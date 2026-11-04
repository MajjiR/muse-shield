"""Small Fireworks training-session operations for robust_train.py (run with the cookbook venv).

    fw_ops.py checkpoints --session <accounts/a/trainingSessions/ts-..>
    fw_ops.py promote --session <..> --run <run-id> --output-model <model-id>   # latest promotable of that run
    fw_ops.py delete-session --session <..>
    fw_ops.py session-state --session <..>

Prints one JSON object. Never touches a session it was not given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BASE_MODEL = "accounts/fireworks/models/muse-glimmer-30b"


def _client():
    from fireworks.training.sdk.fireworks_client import FireworksClient

    return FireworksClient(api_key=os.environ["FIREWORKS_API_KEY"])


def _step(row: dict) -> int:
    name = (row.get("checkpointName") or row.get("name") or "").rsplit("/", 1)[-1]
    digits = "".join(ch for ch in name.rsplit("step-", 1)[-1] if ch.isdigit()) if "step-" in name else ""
    return int(digits) if digits else -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["checkpoints", "promote", "delete-session", "session-state"])
    ap.add_argument("--session", required=True)
    ap.add_argument("--run", default="")
    ap.add_argument("--output-model", default="")
    a = ap.parse_args()
    fw = _client()
    if a.cmd == "checkpoints":
        rows = fw.list_training_session_checkpoints(a.session)
        print(json.dumps([{"name": r.get("name"), "promotable": r.get("promotable"), "step": _step(r)} for r in rows]))
    elif a.cmd == "promote":
        rows = [r for r in fw.list_training_session_checkpoints(a.session)
                if r.get("promotable") and (not a.run or a.run in (r.get("name") or "")) and _step(r) >= 0]
        if not rows:
            print(json.dumps({"promoted": None, "reason": "no promotable checkpoint for this run"}))
            return 1
        best = max(rows, key=_step)
        model_id = a.output_model.rsplit("/", 1)[-1]
        fw.promote_session_checkpoint(name=best["name"], output_model_id=model_id, base_model=BASE_MODEL)
        print(json.dumps({"promoted": model_id, "from_checkpoint": best["name"], "step": _step(best)}))
    elif a.cmd == "delete-session":
        fw.delete_training_session(a.session)
        print(json.dumps({"deleted": a.session}))
    else:
        import httpx

        r = httpx.get(f"https://api.fireworks.ai/v1/{a.session}", headers={"Authorization": f"Bearer {os.environ['FIREWORKS_API_KEY']}"}, timeout=20)
        print(json.dumps({"state": r.json().get("state"), "http": r.status_code}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
