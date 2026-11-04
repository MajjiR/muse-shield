"""Score er-v3 checkpoints while the trainers are still running, so a bad run shows up early.

    python3 scripts/er_ckpt_watch.py --data runs/er/v3

Every minute it reads each launched run's log. For each new promotable checkpoint ("Sampler checkpoint 'step-N'
saved") it promotes the checkpoint to a model (muse-shield-glimmer-er-v3<x>-s<N>), deploys it on a short-lived H200
(scripts/er_deploy_eval.py: deleted in a finally), and scores the HELD-OUT sets only:
- heldout-er-val: our er validation documents (never trained on, not the er test set),
- heldout-v3-val: v3-family documents held out of training,
- heldout-nemotron-train: Nemotron-PII *train* documents held out of training (not the benchmark test docs).
Public benchmarks are never used here. Results land in results/entity-resolution/ (tag er-v3<x>-s<N>) and one
line per checkpoint in <data>/checkpoints.md. It stops when every run has ended and every checkpoint is scored.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
VENV_PY = "/Volumes/MajjiR/ai/venv-fwtrain/bin/python"
PROMOTE = "/Volumes/MajjiR/ai/fw-cookbook/training/examples/tools/promote_checkpoint.py"
BASE = "accounts/fireworks/models/muse-glimmer-30b"
ACCOUNT = "rohan-majji"
ENV_FILE = Path("/Users/majjir/muse-shield/.env")


def log(m: str) -> None:
    print(time.strftime("%H:%M:%S"), m, flush=True)


def env() -> dict:
    e = dict(os.environ)
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            e.setdefault(k.strip(), v.strip().strip('"'))
    return e


def summary(report: Path) -> dict:
    r = json.loads(report.read_text())["sets"]
    out = {}
    for name, s in r.items():
        out[name] = {"valid": s.get("valid"), "leak": s.get("leak"), "core_leak": s.get("core_leak"),
                     "mention_f1": s.get("mention", {}).get("f1"), "coref_f1": s.get("coref", {}).get("f1"),
                     "owner": s.get("owner_acc")}
    return out


def score(variant: str, job: str, step: int, data: Path, e: dict, lock: threading.Lock) -> None:
    tag = f"er-v3{variant.lower()}-s{step}"
    model_id = f"muse-shield-glimmer-{tag}"
    t0 = time.time()
    p = subprocess.run([VENV_PY, PROMOTE, "--job-id", job, "--checkpoint-name", f"step-{step}", "--base-model", BASE,
                        "--output-model-id", model_id], env=e, capture_output=True, text=True)
    if p.returncode:
        log(f"{tag}: promote failed: {p.stderr[-300:]}")
        return
    http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {e['FIREWORKS_API_KEY']}"})
    for _ in range(60):  # promoted models take a moment to become deployable
        st = http.get(f"https://api.fireworks.ai/v1/accounts/{ACCOUNT}/models/{model_id}").json().get("state")
        if st == "READY":
            break
        time.sleep(15)
    sets = [f"{n}={data / f'{n}.docs.jsonl'}" for n in ("heldout-er-val", "heldout-v3-val", "heldout-nemotron-train")]
    p = subprocess.run([VENV_PY, str(REPO / "scripts/er_deploy_eval.py"), model_id, "--tag", tag, "--no-example",
                        "--workers", "32", "--max-tokens", "4000", "--sets", *sets], env=e, capture_output=True, text=True, cwd=REPO)
    rec = re.search(r"recorded (\S+)", p.stdout)
    if not rec:
        log(f"{tag}: eval failed: {(p.stdout + p.stderr)[-500:]}")
        return
    s = summary(Path(rec.group(1)) / "report.json")
    line = f"| {variant} | {step} | " + " | ".join(
        f"{(x['core_leak'] or 0) * 100:.1f}% / {x['coref_f1'] or 0:.3f} / {(x['valid'] or 0) * 100:.0f}%" for x in s.values()) + \
        f" | {(time.time() - t0) / 60:.0f} min |"
    with lock:
        f = data / "checkpoints.md"
        if not f.exists():
            f.write_text("# er-v3 checkpoints on held-out data (core leak / coreference F1 / valid)\n\n"
                         "| run | step | er val (60) | v3 val (80) | Nemotron train held-out (150) | time |\n|---|---|---|---|---|---|\n")
        with f.open("a") as fh:
            fh.write(line + "\n")
        with (data / "checkpoints.jsonl").open("a") as fh:
            fh.write(json.dumps({"variant": variant, "step": step, "model": model_id, "run": rec.group(1), "sets": s}) + "\n")
    log(f"{tag}: {line}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=REPO / "runs/er/v3")
    ap.add_argument("--every", type=int, default=60)
    a = ap.parse_args()
    e = env()
    runs = json.loads((a.data / "launched.json").read_text())
    started: set[tuple[str, int]] = set()
    threads: list[threading.Thread] = []
    lock = threading.Lock()
    while True:
        ended = 0
        for v, r in runs.items():
            text = (Path(r["dir"]) / "run.log").read_text(errors="replace")
            job = re.search(r"Created trainer job: (\S+)", text)
            for step in map(int, re.findall(r"Sampler checkpoint 'step-(\d+)' saved", text)):
                if job and (v, step) not in started:
                    started.add((v, step))
                    log(f"{v}: checkpoint step {step} saved; scoring")
                    t = threading.Thread(target=score, args=(v, job.group(1), step, a.data, e, lock), daemon=False)
                    t.start()
                    threads.append(t)
            ended += bool(re.search(r"Training complete|Traceback|Deleted trainer job", text))
        if ended == len(runs) and all(not t.is_alive() for t in threads):
            log("all runs ended and every checkpoint is scored")
            return 0
        time.sleep(a.every)


if __name__ == "__main__":
    raise SystemExit(main())
