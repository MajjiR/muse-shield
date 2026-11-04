"""python -m muse_shield.app  ->  http://127.0.0.1:8765

Masking runs on our fine-tuned Muse Glimmer. Unless MUSE_SHIELD_GLIMMER_ER_MODEL already names a running
deployment, this brings one up first (see glimmer_instance.py), points the masker at it, and deletes it
when the app stops (Ctrl-C). MUSE_SHIELD_GLIMMER_AUTO=0 skips that; masking is then off.
"""

import os
import signal

import httpx
import uvicorn

from ..config import load_env
from .glimmer_instance import GlimmerInstance, Instance, InstanceError
from .server import create_app


def _interrupt(*_):
    raise KeyboardInterrupt  # a stop signal while Glimmer starts must still clean up


def main() -> int:
    load_env()
    port = int(os.environ.get("PORT", 8765))
    instance = inst = None
    if os.environ.get("MUSE_SHIELD_GLIMMER_AUTO", "1") != "0" and not os.environ.get("MUSE_SHIELD_GLIMMER_ER_MODEL"):
        signal.signal(signal.SIGTERM, _interrupt)
        try:
            instance = GlimmerInstance()
            inst = instance.up()
            os.environ["MUSE_SHIELD_GLIMMER_ER_MODEL"] = inst.route
        except (InstanceError, httpx.HTTPError, OSError) as exc:
            print(f"Glimmer: {exc}. Masking stays off.")
        except KeyboardInterrupt:
            print("Glimmer: stopped while starting.")
            for d in instance._ours() if instance else []:  # one may already have been created
                instance.down(Instance(d["name"].split("/")[-1], ""))
            return 1
    try:
        print(f"Muse Shield: http://127.0.0.1:{port}")
        uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
    finally:
        if inst and instance:
            try:
                instance.down(inst)
            except InstanceError as exc:
                print(f"Glimmer: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
