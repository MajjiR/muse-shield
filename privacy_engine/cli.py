"""privacy-engine CLI: serve the dashboard, or protect / ask from the terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="privacy-engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="run the local dashboard")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))

    for name, help_ in (("protect", "show what the cloud would see"), ("ask", "ask the cloud LLM through the engine")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("text", nargs="?", help="prompt (default: stdin)")
        p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .server import create_app

        print(f"Privacy Engine dashboard: http://127.0.0.1:{args.port}")
        uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
        return 0

    from .pipeline import PrivacyEngine

    text = args.text if args.text is not None else sys.stdin.read()
    engine = PrivacyEngine()
    if args.cmd == "protect":
        result = engine.protect(text)
        print(json.dumps(result.to_dict(), indent=2) if args.json else result.masked.masked)
        return 0

    result = engine.ask(text)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"── sent to {result.cloud} ──\n{result.protected.masked.masked}\n")
        if result.error:
            print(f"── {result.error} ──")
            return 1
        print(f"── answer (restored locally) ──\n{result.answer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
