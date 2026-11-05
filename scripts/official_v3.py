"""Official er-v3 benchmark round: our fine-tune vs Muse Spark vs base Muse Glimmer, same instructions, run once.

    .venv/bin/python scripts/official_v3.py --model muse-shield-glimmer-er-v3a-s250

The model was chosen beforehand on held-out data only (runs/er/v3/checkpoints.md); nothing here feeds back into
training or selection. Deploys our model and base Glimmer on short-lived H200s (deleted in a finally), then runs
in parallel:
- Nemotron-PII: the 500-doc test sample (HF test split, seed 7; muse_shield.benchmarks.run).
- PUPA: the 269 held-out prompts (runs/er/v3/pupa-final.jsonl; never used for a decision).
- TAB: 127 ECHR test judgments (first ~6,000 chars), scored afterwards with scripts/tab_official.py.
- Synthetic: base Glimmer on the ambiguity set (the other synthetic rows already exist for every model).
Every model gets er-v3's v3 instructions (MUSE_SHIELD_ER_PROMPT=v3); Spark and base also get the worked example,
which our fine-tune was trained without. Muse Spark is also run with the app's original analysis prompt on PUPA,
for reference.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import er_ckpt_watch as W  # noqa: E402

BASE = "accounts/fireworks/models/muse-glimmer-30b"


def log(m: str) -> None:
    print(time.strftime("%H:%M:%S"), m, flush=True)


def deploy_base(http: httpx.Client) -> tuple[str, str]:
    api = f"https://api.fireworks.ai/v1/accounts/{W.ACCOUNT}/deployments"
    dep = f"ms-off-base-{time.strftime('%H%M%S')}"
    r = http.post(api, params={"deploymentId": dep}, json={"baseModel": BASE, "deploymentShape": W.SHAPE, "minReplicaCount": 1,
                                                          "maxReplicaCount": 1, "displayName": "muse-shield official base"})
    if r.status_code >= 400:  # the live-merge shape may not take the bare base model: let Fireworks pick a shape
        r = http.post(api, params={"deploymentId": dep}, json={"baseModel": BASE, "minReplicaCount": 1, "maxReplicaCount": 1,
                                                              "acceleratorType": "NVIDIA_H200_141GB", "acceleratorCount": 1,
                                                              "displayName": "muse-shield official base"})
    r.raise_for_status()
    t0 = time.time()
    while (st := http.get(f"{api}/{dep}").json().get("state")) != "READY":
        if st in ("FAILED", "DELETED", "DELETING") or time.time() - t0 > 2400:
            raise RuntimeError(f"{dep} {st}")
        time.sleep(15)
    route = f"{BASE}#accounts/{W.ACCOUNT}/deployments/{dep}"
    for _ in range(40):
        if http.post("https://api.fireworks.ai/inference/v1/chat/completions",
                     json={"model": route, "max_tokens": 4, "messages": [{"role": "user", "content": "ok"}]}).status_code == 200:
            break
        time.sleep(10)
    return dep, route


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="muse-shield-glimmer-er-v3a-s250")
    ap.add_argument("--tag", default="er-v3a")
    a = ap.parse_args()
    e = W.env()
    http = httpx.Client(timeout=120, headers={"Authorization": f"Bearer {e['FIREWORKS_API_KEY']}"})
    deps, results = [], {}
    nemo_cache = "/Users/majjir/muse-shield/runs/benchmarks"
    v3 = {"MUSE_SHIELD_ER_PROMPT": "v3"}
    shot = {"MUSE_SHIELD_ER_EXAMPLE": "1"}

    def run(name: str, cmd: list[str], extra: dict | None = None) -> None:
        t0 = time.time()
        p = subprocess.run(cmd, env={**e, **(extra or {})}, capture_output=True, text=True, cwd=REPO)
        results[name] = (p.returncode, (p.stdout + p.stderr)[-2500:])
        log(f"{name}: exit {p.returncode} in {(time.time() - t0) / 60:.1f} min")

    threads: list[threading.Thread] = []

    def start(*args) -> None:
        t = threading.Thread(target=run, args=args)
        t.start()
        threads.append(t)

    py, vpy = W.PROJECT_PY, W.VENV_PY
    nemo = [py, "-m", "muse_shield.benchmarks.run", "--n", "500", "--workers", "16", "--cache", nemo_cache]
    tab = ["--sets", f"tab={REPO / 'runs/er/tab/tab.docs.jsonl'}", "--relaxed", "--workers", "24", "--max-tokens", "6000"]
    # Spark needs no deployment: start it right away
    start("nemotron-spark", nemo + ["--backends", "muse_spark", "--tag", "official-spark-v3prompt"],
          {"ANALYSIS_TASK": "resolution", "META_SYNTHETIC_ONLY": "1", "META_MAX_TOKENS": "8000", **v3, **shot})
    start("tab-spark", [vpy, "scripts/er_eval.py", "--backend", "muse_spark", "--tag", "official-tab-spark-v3prompt", "--prompt", "v3", *tab])
    try:
        dep_a, route_a = W.deploy(a.model, http)
        deps.append(dep_a)
        log(f"{a.model} serving on {dep_a}")
        start("nemotron-ours", nemo + ["--backends", "glimmer", "--tag", f"official-{a.tag}"],
              {"ANALYSIS_TASK": "resolution", "GLIMMER_MODEL": route_a})
        start("tab-ours", [vpy, "scripts/er_eval.py", "--backend", "glimmer", "--model", route_a, "--tag", f"official-tab-{a.tag}",
                           "--no-example", *tab])
        dep_b, route_b = deploy_base(http)
        deps.append(dep_b)
        log(f"base Glimmer serving on {dep_b}")
        start("nemotron-base", nemo + ["--backends", "glimmer", "--tag", "official-base-v3prompt"],
              {"ANALYSIS_TASK": "resolution", "GLIMMER_MODEL": route_b, **v3, **shot})
        start("tab-base", [vpy, "scripts/er_eval.py", "--backend", "glimmer", "--model", route_b, "--tag", "official-tab-base-v3prompt",
                           "--prompt", "v3", *tab])
        start("synthetic-base-ambiguity", [vpy, "scripts/er_eval.py", "--backend", "glimmer", "--model", route_b, "--tag",
                                           "official-base-ambiguity", "--sets", f"ambiguity={REPO / 'data/er-v1/ambiguity.docs.jsonl'}",
                                           "--workers", "24"])
        start("pupa-final", [py, "scripts/pupa_eval.py", "--prompts", str(REPO / "runs/er/v3/pupa-final.jsonl"),
                             "--er", route_a, "--er-name", f"Muse Glimmer + {a.tag} (ours)",
                             "--er2", route_b, "--er2-name", "Base Muse Glimmer (same instructions)",
                             "--spark-er", "--spark", "--workers", "16", "--tag", f"official-final-{a.tag}"], v3)
        for t in threads:
            t.join()
    finally:
        for d in deps:
            r = http.delete(f"https://api.fireworks.ai/v1/accounts/{W.ACCOUNT}/deployments/{d}", params={"ignoreChecks": "true"})
            log(f"deleted {d} ({r.status_code})")
    for name, (code, out) in results.items():
        print(f"===== {name} (exit {code})\n{out[-1200:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
