"""Score er-v3 checkpoints while the trainers are still running, so a bad run shows up early.

    python3 scripts/er_ckpt_watch.py --data runs/er/v3

Every minute it reads each launched run's log. For each new promotable checkpoint ("Sampler checkpoint 'step-N'
saved") it promotes the checkpoint to a model (muse-shield-glimmer-er-v3<x>-s<N>), deploys it on a short-lived H200
(deleted in a finally; prefix ms-ck-), and scores, in parallel:
- our standard synthetic sets, same as er-v2b's numbers: er test (150), challenge (80), ambiguity (80) — the regression
  gates: a checkpoint below er-v2b there is flagged;
- the weak areas, on held-out slices only: v3-family val (80), 150 Nemotron-PII *train* docs not trained on (the 500
  test docs are untouched), and a 101-prompt PUPA dev slice cut from the PUPA test half (the final PUPA score uses
  only the other 269 prompts, pupa-final.jsonl).
Each checkpoint gets a verdict: continue, or STOP? when it falls below er-v2b on the synthetic gates or stops
improving on the weak areas since the run's previous checkpoint. Results land in results/entity-resolution/,
results/pupa/ and one row per checkpoint in <data>/checkpoints.md. It stops when every run has ended and every checkpoint is scored.
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
PROJECT_PY = "/Users/majjir/muse-shield/.venv/bin/python"
SHAPE = "accounts/fireworks/deploymentShapes/dkuwotf7"  # live-merge H200 BF16


def log(m: str) -> None:
    print(time.strftime("%H:%M:%S"), m, flush=True)


def env() -> dict:
    e = dict(os.environ)
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            e.setdefault(k.strip(), v.strip().strip('"'))
    return e


ER_SETS = {"test": REPO / "data/er-v1/test.docs.jsonl", "challenge": REPO / "data/er-v1/challenge.docs.jsonl",
           "ambiguity": REPO / "data/er-v1/ambiguity.docs.jsonl"}
# er-v2b on the same synthetic sets (results/entity-resolution/*_er-v2b): the bar a checkpoint must not fall below
GATES = {"test": {"core_leak": 0.005, "coref_f1": 0.97, "owner": 0.99}, "challenge": {"core_leak": 0.005, "coref_f1": 0.96},
         "ambiguity": {"core_leak": 0.005, "unknown": 0.95}}


def summary(report: Path) -> dict:
    r = json.loads(report.read_text())["sets"]
    out = {}
    for name, s in r.items():
        out[name] = {"valid": s.get("valid"), "leak": s.get("leak"), "core_leak": s.get("core_leak"),
                     "mention_f1": s.get("mention", {}).get("f1"), "coref_f1": s.get("coref", {}).get("f1"),
                     "owner": s.get("owner_acc"), "unknown": s.get("unknown_acc")}
    return out


def gate_failures(s: dict) -> list[str]:
    bad = []
    for name, g in GATES.items():
        x = s.get(name, {})
        for k, bar in g.items():
            v = x.get(k)
            if v is None:
                continue
            if (k == "core_leak" and v > bar) or (k != "core_leak" and v < bar):
                bad.append(f"{name} {k} {v:.3f} (bar {bar})")
    return bad


def deploy(model_id: str, http: httpx.Client) -> tuple[str, str]:
    api = f"https://api.fireworks.ai/v1/accounts/{ACCOUNT}/deployments"
    model = f"accounts/{ACCOUNT}/models/{model_id}"
    dep = f"ms-ck-{model_id.split('glimmer-')[-1]}-{time.strftime('%H%M%S')}".replace(".", "-")[:60]
    r = http.post(api, params={"deploymentId": dep}, json={"baseModel": model, "deploymentShape": SHAPE, "minReplicaCount": 1,
                                                          "maxReplicaCount": 1, "displayName": f"muse-shield checkpoint {model_id}"})
    r.raise_for_status()
    t0 = time.time()
    while (st := http.get(f"{api}/{dep}").json().get("state")) != "READY":
        if st in ("FAILED", "DELETED", "DELETING") or time.time() - t0 > 2400:
            raise RuntimeError(f"{dep} {st}")
        time.sleep(15)
    route = f"{model}#accounts/{ACCOUNT}/deployments/{dep}"
    for _ in range(40):
        pr = http.post("https://api.fireworks.ai/inference/v1/chat/completions",
                       json={"model": route, "max_tokens": 4, "messages": [{"role": "user", "content": "ok"}]})
        if pr.status_code == 200:
            break
        time.sleep(10)
    return dep, route


def score(variant: str, job: str, step: int, data: Path, e: dict, lock: threading.Lock) -> None:
    tag = f"er-v3{variant.lower()}-s{step}"
    model_id = f"muse-shield-glimmer-{tag}"
    t0 = time.time()
    p = subprocess.run([VENV_PY, PROMOTE, "--job-id", job, "--checkpoint-name", f"step-{step}", "--base-model", BASE,
                        "--output-model-id", model_id], env=e, capture_output=True, text=True)
    if p.returncode:
        log(f"{tag}: promote failed: {p.stderr[-300:]}")
        return
    http = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {e['FIREWORKS_API_KEY']}"})
    for _ in range(60):  # promoted models take a moment to become deployable
        if http.get(f"https://api.fireworks.ai/v1/accounts/{ACCOUNT}/models/{model_id}").json().get("state") == "READY":
            break
        time.sleep(15)
    dep = None
    try:
        dep, route = deploy(model_id, http)
        log(f"{tag}: serving on {dep}")
        sets = [f"{n}={pth}" for n, pth in ER_SETS.items()] + \
               [f"{n}={data / f'{n}.docs.jsonl'}" for n in ("heldout-v3-val", "heldout-nemotron-train")]
        er = subprocess.Popen([VENV_PY, str(REPO / "scripts/er_eval.py"), "--backend", "glimmer", "--model", route, "--tag", tag,
                               "--no-example", "--workers", "48", "--max-tokens", "4000", "--sets", *sets],
                              env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=REPO)
        pu = subprocess.Popen([PROJECT_PY, str(REPO / "scripts/pupa_eval.py"), "--prompts", str(data / "pupa-dev.jsonl"),
                               "--er", route, "--er-name", f"Muse Glimmer + {tag} (ours)", "--workers", "24", "--tag", f"dev-{tag}"],
                              env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=REPO)
        er_out, pu_out = er.communicate()[0], pu.communicate()[0]
    except Exception as exc:  # noqa: BLE001
        log(f"{tag}: scoring failed: {exc!s:.300}")
        return
    finally:
        if dep:
            r = http.delete(f"https://api.fireworks.ai/v1/accounts/{ACCOUNT}/deployments/{dep}", params={"ignoreChecks": "true"})
            log(f"{tag}: deleted {dep} ({r.status_code})")
    rec = re.search(r"recorded (\S+)", er_out)
    prec = re.search(r"recorded (\S+)", pu_out)
    if not rec or not prec:
        log(f"{tag}: eval failed: {er_out[-400:]} {pu_out[-400:]}")
        return
    s = summary(Path(rec.group(1)) / "report.json")
    pj = json.loads((Path(prec.group(1)) / "report.json").read_text())
    pupa = next(iter(pj.values()))
    s["pupa-dev"] = {"leak": pupa["leak_rate"], "protected": pupa["prompts_fully_protected"], "valid": pupa["valid"]}
    bad = gate_failures(s)
    with lock:
        hist = [json.loads(l) for l in (data / "checkpoints.jsonl").read_text().splitlines()] if (data / "checkpoints.jsonl").exists() else []
        prev = [h for h in hist if h["variant"] == variant]
        prev = prev[-1]["sets"] if prev else None
        weak = lambda x: (x["pupa-dev"]["leak"], x["heldout-nemotron-train"]["core_leak"], x["heldout-v3-val"]["core_leak"])  # noqa: E731
        if bad and len(bad) >= 3:
            verdict = "STOP? below er-v2b on " + "; ".join(bad)
        elif prev and all(a >= b - 0.002 for a, b in zip(weak(s), weak(prev))):
            verdict = "STOP? no gain since last checkpoint on PUPA dev, Nemotron held-out or v3 val"
        else:
            verdict = "continue" + (f" (watch: {'; '.join(bad)})" if bad else "")
        f = data / "checkpoints.md"
        if not f.exists():
            f.write_text("# er-v3 checkpoints (core leak; coreference F1 for the synthetic sets)\n\n"
                         "PUPA dev = 101 prompts from the PUPA test half, never used for the final score (pupa-final, 269 prompts).\n"
                         "Nemotron held-out = 150 Nemotron *train* docs not trained on; the 500 test docs are untouched.\n\n"
                         "| run | step | ER test | challenge | ambiguity (UNKNOWN) | v3 val | Nemotron held-out | PUPA dev leak | verdict |\n"
                         "|---|---|---|---|---|---|---|---|---|\n"
                         "| er-v2b | — | 0.1% / 0.979 | 0.3% / 0.968 | 0.2% (96%) | — | — | — | baseline |\n"
                         "| Muse Spark | — | — | — | — | — | — | 6.1% | baseline |\n")
        pct = lambda v: f"{(v or 0) * 100:.1f}%"  # noqa: E731
        line = (f"| {variant} | {step} | {pct(s['test']['core_leak'])} / {s['test']['coref_f1']:.3f} | "
                f"{pct(s['challenge']['core_leak'])} / {s['challenge']['coref_f1']:.3f} | "
                f"{pct(s['ambiguity']['core_leak'])} ({pct(s['ambiguity']['unknown'])}) | {pct(s['heldout-v3-val']['core_leak'])} | "
                f"{pct(s['heldout-nemotron-train']['core_leak'])} | {pct(s['pupa-dev']['leak'])} | {verdict} |")
        with f.open("a") as fh:
            fh.write(line + "\n")
        with (data / "checkpoints.jsonl").open("a") as fh:
            fh.write(json.dumps({"variant": variant, "step": step, "model": model_id, "run": rec.group(1), "pupa_run": prec.group(1),
                                 "sets": s, "verdict": verdict, "minutes": round((time.time() - t0) / 60, 1)}) + "\n")
    log(f"CHECKPOINT {line}")


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
