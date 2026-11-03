"""Supervised, resumable Fireworks LoRA fine-tuning for Muse Glimmer.

    python3 scripts/robust_train.py --name glimmer-lora-v1c \\
        --train /path/train.jsonl --eval /path/val.jsonl --out results/training/<run-dir>

What it adds on top of the cookbook SFT loop (scripts/sft_entry.py):
- **Checkpoints** every --checkpoint-every steps, resumable and promotable.
- **Crash recovery:** if the trainer process dies, it resumes from the newest checkpoint of the
  same run (same log path and data cursor) instead of starting over, up to --max-attempts.
  A run still holding Fireworks' one training slot (429 "maximum concurrent ... runs") is cleared
  only if it is one of *this* run's own sessions. An account suspension (HTTP 412) stops
  everything and reports, since retrying cannot help.
- **Health checks** on every logged step:
  - divergence: NaN/inf loss, or the smoothed loss rising above 2x its best for 3 checks;
  - plateau: the smoothed loss improving less than --plateau-min-improve over two consecutive
    --plateau-window spans, after --min-steps.

  Either one stops the run early and promotes the newest promotable checkpoint (unless
  --no-early-stop). health.jsonl records every check.
- **Records** (in --out): steps.csv (plotting), metrics.jsonl (raw), health.jsonl, state.json
  (attempts, resume refs, sessions, outcome), stats.json (timing, loss, eval, model),
  loss.html, and one log per attempt.
- **Cleanup:** the run's training session is deleted after the model is promoted, so the next
  run can start (Fireworks allows one serverless Glimmer run at a time).

Overfitting note: inside one epoch every batch is unseen, so the training loss is a held-out
signal. The eval loss on --eval is logged at the start and at each epoch end. Multi-epoch runs
should rely on it.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VENV_PY = "/Volumes/MajjiR/ai/venv-fwtrain/bin/python"
COOKBOOK = "/Volumes/MajjiR/ai/fw-cookbook/training"
ENV_FILE = Path("/Users/majjir/muse-shield/.env")


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_env() -> dict:
    env = dict(os.environ)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    env.update({"HF_HOME": "/Volumes/MajjiR/ai/caches/huggingface", "TMPDIR": "/Volumes/MajjiR/ai/caches/tmp",
                "FIREWORKS_CLIENT_SOURCE": "fireworks-training-skill/2.3.0", "PYTHONUNBUFFERED": "1"})
    return env


def fw_ops(env: dict, *args: str) -> dict:
    r = subprocess.run([VENV_PY, str(REPO / "scripts" / "fw_ops.py"), *args], capture_output=True, text=True, env=env, cwd=COOKBOOK)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"error": (r.stderr or r.stdout)[-400:]}


class Health:
    def __init__(self, window: int, min_improve: float, min_steps: int, alpha: float = 0.1):
        self.window, self.min_improve, self.min_steps, self.alpha = window, min_improve, min_steps, alpha
        self.ema: float | None = None
        self.history: dict[int, float] = {}
        self.best = math.inf
        self.rising = 0
        self.flat_windows = 0
        self.last_window_step = 0

    def update(self, step: int, loss: float) -> dict | None:
        if math.isnan(loss) or math.isinf(loss):
            return {"verdict": "diverged", "reason": f"loss is {loss} at step {step}"}
        self.ema = loss if self.ema is None else self.alpha * loss + (1 - self.alpha) * self.ema
        self.history[step] = self.ema
        self.best = min(self.best, self.ema)
        if step >= self.min_steps and self.ema > 2 * self.best:
            self.rising += 1
            if self.rising >= 3:
                return {"verdict": "diverged", "reason": f"smoothed loss {self.ema:.4f} > 2x best {self.best:.4f} for 3 checks"}
        else:
            self.rising = 0
        if step >= self.min_steps and step - self.last_window_step >= self.window:
            past = [s for s in self.history if s <= step - self.window]
            if past:
                before = self.history[max(past)]
                improve = (before - self.ema) / before if before > 0 else 0.0
                self.flat_windows = self.flat_windows + 1 if improve < self.min_improve else 0
                self.last_window_step = step
                verdict = {"verdict": "plateau" if self.flat_windows >= 2 else "ok", "step": step, "ema": self.ema,
                           "improve_over_window": improve, "flat_windows": self.flat_windows}
                if self.flat_windows >= 2:
                    verdict["reason"] = (f"smoothed loss improved <{self.min_improve:.0%} in each of the last 2 windows "
                                         f"of {self.window} steps")
                return verdict
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="robust_train.py")
    ap.add_argument("--name", required=True)
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--eval", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--output-model-id", default="")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--max-seq-len", type=int, default=2048)
    ap.add_argument("--warmup-steps", type=int, default=0)
    ap.add_argument("--max-examples", type=int, default=None)
    ap.add_argument("--checkpoint-every", type=int, default=25)
    ap.add_argument("--max-attempts", type=int, default=5)
    ap.add_argument("--plateau-window", type=int, default=50)
    ap.add_argument("--plateau-min-improve", type=float, default=0.02)
    ap.add_argument("--min-steps", type=int, default=100)
    ap.add_argument("--no-early-stop", action="store_true")
    ap.add_argument("--simulate-crash-at", type=int, default=0, help="test only: kill attempt 1 at this step")
    a = ap.parse_args(argv)

    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "trainer"
    log_path.mkdir(exist_ok=True)
    model_id = a.output_model_id or f"muse-shield-{a.name}"
    env = load_env()
    env.update({"COOKBOOK_METRICS_FILE": str(out / "metrics.jsonl"), "COOKBOOK_STATUS_FILE": str(out / "status.json"),
                "COOKBOOK_OUTPUT_MODEL_PATH": str(out / "output_model.json")})
    state_file = out / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {
        "name": a.name, "model_id": model_id, "attempts": [], "sessions": [], "runs": [], "outcome": None,
        "params": {k: v for k, v in vars(a).items() if k not in ("train", "eval", "out")},
        "train": str(a.train), "eval": str(a.eval) if a.eval else None, "started": time.time()}

    def save() -> None:
        state_file.write_text(json.dumps(state, indent=2, default=str))

    health = Health(a.plateau_window, a.plateau_min_improve, a.min_steps)
    seen_steps: set[int] = set()
    metrics_pos = 0
    csv_new = not (out / "steps.csv").exists()
    if not csv_new:  # supervisor restarted: continue where the records end instead of re-reading them
        for r in csv.DictReader((out / "steps.csv").open()):
            seen_steps.add(int(r["step"]))
            health.update(int(r["step"]), float(r["loss"]))
        metrics_pos = len((out / "metrics.jsonl").read_text()) if (out / "metrics.jsonl").exists() else 0

    def ingest() -> dict | None:
        """Read new metrics lines into steps.csv and run health checks. Returns a stop verdict."""
        nonlocal metrics_pos, csv_new
        mf = out / "metrics.jsonl"
        if not mf.exists():
            return None
        text = mf.read_text()
        new, metrics_pos = text[metrics_pos:], len(text)
        stop = None
        rows = []
        for line in new.splitlines():
            try:
                m = json.loads(line)
            except ValueError:
                continue
            step = m.get("step")
            loss = next((m[k] for k in ("train/ce_loss", "train/loss", "loss", "train/mean_nll") if k in m), None)
            if "eval/loss" in m:
                with (out / "health.jsonl").open("a") as f:
                    f.write(json.dumps({"t": time.time(), "step": step, "eval_loss": m["eval/loss"]}) + "\n")
                log(f"eval loss at step {step}: {m['eval/loss']:.4f}")
            if step is None or loss is None or step in seen_steps:
                continue
            seen_steps.add(step)
            gn = next((m[k] for k in ("train/grad_norm", "grad_norm", "train/grad_norm_pre_clip") if k in m), "")
            rows.append({"step": step, "loss": loss, "grad_norm": gn, "observed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "elapsed_s": round(time.time() - state["started"], 1)})
            verdict = health.update(step, float(loss))
            if verdict:
                with (out / "health.jsonl").open("a") as f:
                    f.write(json.dumps({"t": time.time(), **verdict}) + "\n")
                if verdict["verdict"] != "ok":
                    stop = verdict
            if step % 25 == 0:
                log(f"step {step} loss {float(loss):.4f} ema {health.ema:.4f}")
        if rows:
            with (out / "steps.csv").open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["step", "loss", "grad_norm", "observed_utc", "elapsed_s"])
                if csv_new:
                    w.writeheader()
                    csv_new = False
                w.writerows(rows)
        return stop

    resume_ref = state.get("resume_ref")
    while len(state["attempts"]) < a.max_attempts:
        n = len(state["attempts"]) + 1
        cfg = {"cookbook_training_dir": str(Path(COOKBOOK).parent), "log_path": str(log_path),
               "base_model": "accounts/fireworks/models/muse-glimmer-30b", "tokenizer_model": "meta-models/Muse-Glimmer-30B",
               "renderer_name": "muse_glimmer", "train_file": str(a.train), "eval_file": str(a.eval) if a.eval else "",
               "lora_rank": a.rank, "learning_rate": a.lr, "epochs": a.epochs, "batch_size": a.batch, "max_seq_len": a.max_seq_len,
               "warmup_steps": a.warmup_steps, "checkpoint_every": a.checkpoint_every, "init_from_checkpoint": resume_ref,
               "output_model_id": model_id, "max_examples": a.max_examples}
        (out / f"attempt-{n}.config.json").write_text(json.dumps(cfg, indent=2))
        attempt_log = out / f"attempt-{n}.log"
        log(f"attempt {n} starting" + (f", resuming from {resume_ref}" if resume_ref else ", fresh start"))
        att = {"n": n, "start": time.time(), "resume_ref": resume_ref}
        state["attempts"].append(att)
        save()
        with attempt_log.open("w") as lf:
            child = subprocess.Popen([VENV_PY, str(REPO / "scripts" / "sft_entry.py"), "--config", str(out / f"attempt-{n}.config.json")],
                                     cwd=COOKBOOK, env=env, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
        stop_verdict = None
        simulated = False
        while child.poll() is None:
            time.sleep(10)
            txt = attempt_log.read_text(errors="replace")
            for sess in set(re.findall(r"accounts/[\w-]+/trainingSessions/ts-[0-9a-f]+", txt)) | {
                    f"accounts/rohan-majji/trainingSessions/{s}" for s in re.findall(r"\b(ts-[0-9a-f]{32})\b", txt)}:
                if sess not in state["sessions"]:
                    state["sessions"].append(sess)
                    log(f"session {sess}")
            for run in set(re.findall(r"\b(run-[0-9a-f]{32})\b", txt)):
                if run not in state["runs"]:
                    state["runs"].append(run)
                    log(f"run {run}")
            save()
            v = ingest()
            if v and not a.no_early_stop:
                stop_verdict = v
                log(f"EARLY STOP: {v['verdict']}: {v.get('reason')}")
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                break
            if a.simulate_crash_at and n == 1 and max(seen_steps, default=0) >= a.simulate_crash_at and not simulated:
                simulated = True
                log(f"TEST: simulating a crash at step {max(seen_steps)}")
                os.killpg(child.pid, signal.SIGKILL)
        code = child.wait()
        ingest()
        att.update({"end": time.time(), "exit": code, "last_step": max(seen_steps, default=0)})
        tail = attempt_log.read_text(errors="replace")[-6000:]

        if stop_verdict:
            att["outcome"] = f"early stop ({stop_verdict['verdict']})"
            state["early_stop"] = stop_verdict
            promo = fw_ops(env, "promote", "--session", state["sessions"][-1], "--run", state["runs"][-1] if state["runs"] else "",
                           "--output-model", model_id) if state["sessions"] else {"promoted": None, "reason": "no session seen"}
            state["promotion"] = promo
            state["outcome"] = "early_stopped"
            log(f"promotion after early stop: {promo}")
            break
        if code == 0:
            att["outcome"] = "completed"
            state["outcome"] = "completed"
            if (out / "output_model.json").exists():
                state["promotion"] = json.loads((out / "output_model.json").read_text())
            log(f"attempt {n} completed; model {state.get('promotion')}")
            break
        if "suspended" in tail or "412" in tail and "PRECONDITION_FAILED" in tail:
            att["outcome"] = "account suspended"
            state["outcome"] = "blocked: Fireworks account suspended (billing)"
            log("STOP: Fireworks account suspended; retrying cannot help")
            break
        if "maximum concurrent serverless training runs" in tail:
            att["outcome"] = "training slot busy"
            freed = [fw_ops(env, "delete-session", "--session", s) for s in state["sessions"][:-1] or state["sessions"]]
            log(f"slot busy; freed own sessions: {freed}" if freed else "slot busy and no session of ours to free: waiting 5 min")
            time.sleep(30 if freed else 300)
            continue
        att["outcome"] = "crashed" if not simulated else "simulated crash"
        refs = sorted({int(s) for s in re.findall(r"step-(\d+)", (log_path / "dataloader.json").read_text())}) if (log_path / "dataloader.json").exists() else []
        if refs and state["runs"]:
            resume_ref = f"rohan-majji/{state['runs'][-1]}/step-{refs[-1]}"
            state["resume_ref"] = resume_ref
            log(f"attempt {n} exited {code}; will resume from {resume_ref}")
        else:
            log(f"attempt {n} exited {code} before any checkpoint; restarting fresh")
        save()
        time.sleep(min(30 * n, 120))
    else:
        state["outcome"] = state.get("outcome") or f"gave up after {a.max_attempts} attempts"

    # Free the slot for the next run once the model exists (the session keeps its checkpoints
    # until deleted; the promoted model is independent of it).
    if state.get("promotion") and (state["promotion"].get("model_id") or state["promotion"].get("promoted")):
        state["session_cleanup"] = [fw_ops(env, "delete-session", "--session", s) for s in state["sessions"]]
    state["finished"] = time.time()
    save()
    steps = list(csv.DictReader((out / "steps.csv").open())) if (out / "steps.csv").exists() else []
    losses = [float(r["loss"]) for r in steps]
    evals = [json.loads(l) for l in (out / "health.jsonl").read_text().splitlines() if '"eval_loss"' in l] if (out / "health.jsonl").exists() else []
    stats = {"run": a.name, "outcome": state["outcome"], "model": state.get("promotion"), "early_stop": state.get("early_stop"),
             "params": state["params"], "train": state["train"], "eval": state["eval"],
             "attempts": [{k: v for k, v in x.items() if k != "resume_ref"} | {"resumed_from": x.get("resume_ref")} for x in state["attempts"]],
             "timing": {"wall_seconds": round(state["finished"] - state["started"], 1),
                        # an attempt without a recorded end (its supervisor was stopped) counts as zero
                        "training_seconds": round(sum(max(0.0, x.get("end", x["start"]) - x["start"]) for x in state["attempts"]), 1)},
             "steps": len(losses), "loss": {"first5": sum(losses[:5]) / max(1, len(losses[:5])) if losses else None,
                                            "last5": sum(losses[-5:]) / max(1, len(losses[-5:])) if losses else None,
                                            "min": min(losses) if losses else None},
             "eval_loss": [{"step": e["step"], "loss": e["eval_loss"]} for e in evals],
             "cost_usd": {"training": 0.0, "basis": "Muse Glimmer LoRA SFT promotion (jobs before 2026-12-01T00:00:00-08:00)"}}
    (out / "stats.json").write_text(json.dumps(stats, indent=2, default=str))
    if steps:
        subprocess.run([sys.executable, str(REPO / "scripts" / "plot_training.py"), str(out)], check=False)
    log(f"DONE: {state['outcome']}")
    return 0 if state["outcome"] in ("completed", "early_stopped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
