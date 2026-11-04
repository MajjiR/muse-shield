"""Keep one fine-tuned entity-resolution model deployed while someone tests it, then remove it.

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_serve.py up muse-shield-glimmer-er-v2a   # prints the route
    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_serve.py down <deployment id>

`up` uses one warm replica (min 1) so the first request doesn't wait for a cold start: it bills $8/h
until `down`. The route goes to runs/er/serve.json, which the playground reads.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from fireworks import Fireworks

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_adapters import ACCOUNT, load_env, log, shape_for, wait_serving  # noqa: E402

STATE = Path(__file__).resolve().parents[1] / "runs/er/serve.json"


def main(argv: list[str]) -> int:
    env = load_env()
    os.environ["FIREWORKS_API_KEY"] = env["FIREWORKS_API_KEY"]
    client = Fireworks(account_id=ACCOUNT)
    if argv[0] == "down":
        client.deployments.delete(argv[1], ignore_checks=True)
        log(f"deleted {argv[1]}")
        if STATE.exists() and json.loads(STATE.read_text()).get("deployment") == argv[1]:
            STATE.unlink()
        return 0
    model_id = argv[1]
    model = f"accounts/{ACCOUNT}/models/{model_id}"
    dep_id = f"ms-er-play-{model_id[-3:]}-{time.strftime('%m%d-%H%M')}".replace(".", "-").replace("_", "-")
    route = f"{model}#accounts/{ACCOUNT}/deployments/{dep_id}"
    client.deployments.create(base_model=model, deployment_id=dep_id, deployment_shape=shape_for(client, model),
                              min_replica_count=1, max_replica_count=1, display_name=f"muse-shield er playground {model_id}")
    log(f"creating {dep_id}")
    wait_serving(client, dep_id, route, env["FIREWORKS_API_KEY"])
    STATE.write_text(json.dumps({"model": model_id, "deployment": dep_id, "route": route, "since": time.time()}))
    log(f"serving {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
