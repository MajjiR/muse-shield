"""Evaluate LoRA adapters one at a time on short-lived live-merge deployments.

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/eval_adapters.py v1c:muse-shield-glimmer-lora-v1c ...

For each adapter: create an H200 live-merge deployment (the adapter merged into Glimmer, min
replicas 0), wait for READY and a real 200 response, run the Nemotron 500, synthetic contract and
sector evals, then delete the deployment. Deletion is in a `finally` with ignore_checks (Fireworks
otherwise refuses to delete a deployment that served requests in the last hour), so a failed
eval doesn't leave a GPU billing. If this process is killed, delete `ms-eval-*` by hand. Progress goes to stdout; results go to the registry as usual.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from fireworks import Fireworks

REPO = Path(__file__).resolve().parents[1]
PY = "/Users/majjir/muse-shield/.venv/bin/python"
ACCOUNT = "rohan-majji"
SHAPE_GPU = "NVIDIA_H200_141GB"


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def load_env() -> dict:
    env = dict(os.environ)
    for line in (REPO / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"'))
    return env


def shape_for(client: Fireworks, model: str) -> str:
    vs = client.deployment_shape_versions.match_for_model(model).deployment_shape_versions or []
    shapes = [v.snapshot for v in vs if getattr(v, "snapshot", None)]
    h200 = [s for s in shapes if getattr(s, "accelerator_type", None) == SHAPE_GPU and getattr(s, "precision", None) == "BF16"]
    if not h200:
        raise SystemExit(f"no H200 BF16 shape for {model}: {[s.name for s in shapes]}")
    return h200[0].name.split("/versions/")[0]


def wait_serving(client: Fireworks, dep_id: str, route: str, key: str, limit_s: int = 3600) -> None:
    t0 = time.monotonic()
    while (d := client.deployments.get(dep_id)).state != "READY":
        if d.state in ("FAILED", "DELETING", "DELETED") or time.monotonic() - t0 > limit_s:
            raise RuntimeError(f"deployment {dep_id} is {d.state}: {d.status}")
        time.sleep(20)
    log(f"{dep_id} READY after {time.monotonic() - t0:.0f}s; probing")
    for i in range(30):  # READY does not prove serving: wait for a real 200
        r = httpx.post("https://api.fireworks.ai/inference/v1/chat/completions", timeout=120,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": route, "max_tokens": 8, "messages": [{"role": "user", "content": "Say ok."}]})
        if r.status_code == 200:
            log(f"{dep_id} serving (probe {i + 1})")
            return
        time.sleep(10)
    raise RuntimeError(f"{dep_id} READY but probe failed: {r.status_code} {r.text[:200]}")


def run_evals(name: str, route: str, env: dict) -> list[tuple[str, int]]:
    e = {**env, "GLIMMER_MODEL": route, "GLIMMER_DEPLOYMENT": ""}
    jobs = [
        ("nemotron", [PY, "-m", "muse_shield.benchmarks.run", "--backends", "glimmer", "--n", "500", "--workers", "16",
                      "--cache", str(REPO.parents[1] / "runs" / "benchmarks"), "--tag", f"full500-glimmer-{name}"]),
        ("synthetic", [PY, "-m", "muse_shield.evals", "--backend", "glimmer", "--n", "60", "--workers", "16",
                       "--tag", f"synthetic-glimmer-{name}"]),
        ("sectors", [PY, "-m", "muse_shield.sector_eval", "--backend", "glimmer", "--workers", "16",
                     "--tag", f"sectors-glimmer-{name}"]),
    ]
    out = []
    for label, cmd in jobs:
        t0 = time.monotonic()
        logf = REPO / "runs" / "adapter-evals" / f"{name}-{label}.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        code = subprocess.call(cmd, cwd=REPO, env=e, stdout=logf.open("w"), stderr=subprocess.STDOUT)
        tail = [l for l in logf.read_text().splitlines() if l.startswith(("n=", "recorded", "| valid JSON (after", "| entity precision"))]
        log(f"{name} {label} exit {code} in {time.monotonic() - t0:.0f}s: " + " | ".join(tail))
        out.append((label, code))
    return out


def main(argv: list[str]) -> int:
    env = load_env()
    key = env["FIREWORKS_API_KEY"]
    os.environ["FIREWORKS_API_KEY"] = key
    client = Fireworks(account_id=ACCOUNT)
    failed = 0
    for spec in argv:
        name, model_id = spec.split(":", 1)
        model = f"accounts/{ACCOUNT}/models/{model_id}"
        dep_id = f"ms-eval-{name}".replace(".", "-")[:60]
        route = f"{model}#accounts/{ACCOUNT}/deployments/{dep_id}"
        t0 = time.monotonic()
        try:
            shape = shape_for(client, model)
            existing = {d.name.split("/")[-1] for d in client.deployments.list().deployments}
            if dep_id in existing:  # a previous runner was stopped after creating it: reuse
                log(f"{name}: reusing existing deployment {dep_id}")
            else:
                log(f"{name}: creating live-merge deployment {dep_id} on {shape}")
                client.deployments.create(base_model=model, deployment_id=dep_id, deployment_shape=shape,
                                          min_replica_count=0, max_replica_count=1, display_name=f"muse-shield eval {name}")
            wait_serving(client, dep_id, route, key)
            t_ready = time.monotonic()
            res = run_evals(name, route, env)
            failed += sum(code != 0 for _, code in res)
            log(f"{name}: evals took {time.monotonic() - t_ready:.0f}s on GPU (startup {t_ready - t0:.0f}s, not billed)")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"{name}: FAILED {exc}")
        finally:
            try:
                client.deployments.delete(dep_id, ignore_checks=True)  # it just served our evals; the recent-traffic check would refuse
                log(f"{name}: deleted {dep_id}")
            except Exception as exc:  # noqa: BLE001
                log(f"{name}: DELETE FAILED for {dep_id}: {exc} (still billing: delete it by hand)")
    log(f"ALL DONE, {failed} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
