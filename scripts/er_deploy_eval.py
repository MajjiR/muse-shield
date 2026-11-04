"""Deploy a fine-tuned model on a short-lived live-merge H200, run the entity-resolution eval, delete it.

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_deploy_eval.py muse-shield-glimmer-er-v1 --tag er-v1

Deletion is in a `finally` with ignore_checks, so a failed eval doesn't leave a GPU billing ($8/h).
If this process is killed, delete `ms-er-*` deployments by hand.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from fireworks import Fireworks

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_adapters import ACCOUNT, load_env, log, shape_for, wait_serving  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    model_id, rest = argv[0], argv[1:]
    env = load_env()
    os.environ["FIREWORKS_API_KEY"] = env["FIREWORKS_API_KEY"]
    client = Fireworks(account_id=ACCOUNT)
    model = model_id if "/" in model_id else f"accounts/{ACCOUNT}/models/{model_id}"
    dep_id = f"ms-er-{model_id.split('/')[-1][-20:]}-{time.strftime('%m%d-%H%M')}".replace(".", "-").replace("_", "-")[:60]
    route = f"{model}#accounts/{ACCOUNT}/deployments/{dep_id}"
    t0 = time.monotonic()
    code = 1
    try:
        shape = shape_for(client, model)
        log(f"creating live-merge deployment {dep_id} on {shape}")
        client.deployments.create(base_model=model, deployment_id=dep_id, deployment_shape=shape,
                                  min_replica_count=0, max_replica_count=1, display_name=f"muse-shield er eval {model_id}")
        wait_serving(client, dep_id, route, env["FIREWORKS_API_KEY"])
        t_ready = time.monotonic()
        code = subprocess.run([sys.executable, str(REPO / "scripts" / "er_eval.py"), "--backend", "glimmer", "--model", route, *rest],
                              env={**env, **os.environ}).returncode
        log(f"eval took {time.monotonic() - t_ready:.0f}s on GPU (startup {t_ready - t0:.0f}s)")
    finally:
        try:
            client.deployments.delete(dep_id, ignore_checks=True)
            log(f"deleted {dep_id}")
        except Exception as exc:  # noqa: BLE001
            log(f"DELETE FAILED for {dep_id}: {exc} (still billing: delete it by hand)")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
