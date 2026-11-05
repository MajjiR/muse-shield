"""python -m muse_shield.app  ->  http://127.0.0.1:8765

Masking runs on our fine-tuned Muse Glimmer. Unless MUSE_SHIELD_GLIMMER_ER_MODEL already names a running
deployment, this brings one up (see glimmer_instance.py) and deletes it when the app stops (Ctrl-C).
The app serves at once while that happens, so you can open it and sign in to Connections; masking switches
on by itself when the model answers. MUSE_SHIELD_GLIMMER_AUTO=0 skips that; masking is then off.
"""

import os
import threading

import httpx
import uvicorn

from ..config import load_env
from .glimmer_instance import GlimmerInstance, Instance, InstanceError
from .server import create_app


class _Swappable:
    """The ASGI app uvicorn serves. It starts without masking and is swapped for one with masking once the
    fine-tuned Glimmer answers (the app has no lifespan hooks, so a swap is all it takes)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)


def _bring_up(instance: GlimmerInstance, served: _Swappable, state: dict) -> None:
    try:
        state["inst"] = inst = instance.up()
        os.environ["MUSE_SHIELD_GLIMMER_ER_MODEL"] = inst.route
        os.environ.pop("MUSE_SHIELD_GLIMMER_STARTING", None)
        served.app = create_app()
        print("Glimmer: ready, masking is on.")
    except (InstanceError, httpx.HTTPError, OSError) as exc:
        os.environ.pop("MUSE_SHIELD_GLIMMER_STARTING", None)
        os.environ["MUSE_SHIELD_GLIMMER_FAILED"] = str(exc)
        served.app = create_app()
        print(f"Glimmer: {exc}. Masking stays off.")


def main() -> int:
    load_env()
    port = int(os.environ.get("PORT", 8765))
    instance, state = None, {}
    if os.environ.get("MUSE_SHIELD_GLIMMER_AUTO", "1") != "0" and not os.environ.get("MUSE_SHIELD_GLIMMER_ER_MODEL"):
        try:
            instance = GlimmerInstance()
            os.environ["MUSE_SHIELD_GLIMMER_STARTING"] = "1"
        except InstanceError as exc:
            print(f"Glimmer: {exc}. Masking stays off.")
    served = _Swappable(create_app())
    if instance:
        threading.Thread(target=_bring_up, args=(instance, served, state), daemon=True).start()
    try:
        print(f"Muse Shield: http://127.0.0.1:{port}")
        uvicorn.run(served, host="127.0.0.1", port=port, log_level="warning")
    finally:
        if instance:
            # Delete what we started, also when we stop before it finished starting.
            deps = [state["inst"]] if state.get("inst") else [Instance(d["name"].split("/")[-1], "") for d in instance._ours()]
            for d in deps:
                try:
                    instance.down(d)
                except (InstanceError, httpx.HTTPError) as exc:
                    print(f"Glimmer: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
