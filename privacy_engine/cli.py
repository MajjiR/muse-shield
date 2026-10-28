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

    sub.add_parser("demo", help="scripted run ending in a leak audit (uses a throwaway vault)")

    bench = sub.add_parser("bench", help="benchmark privacy vs utility on synthetic data")
    bench.add_argument("--n", type=int, default=160)
    bench.add_argument("--seed", type=int, default=7)
    bench.add_argument("--llm", action="store_true", help="include the local Llama detector")
    bench.add_argument("--online", type=int, default=0, metavar="K",
                       help="also score K samples per strategy against the cloud model (sends synthetic raw prompts)")

    lora = sub.add_parser("lora-data", help="export LoRA training data for the local detector, personalized from Teach")
    lora.add_argument("--n", type=int, default=600)
    lora.add_argument("--seed", type=int, default=11)
    lora.add_argument("--out", default="runs/lora")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .server import create_app

        print(f"Privacy Engine dashboard: http://127.0.0.1:{args.port}")
        uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
        return 0

    from .pipeline import PrivacyEngine

    if args.cmd == "demo":
        return demo()
    if args.cmd == "bench":
        return run_bench(args)
    if args.cmd == "lora-data":
        from pathlib import Path

        from .lora import export

        print(json.dumps(export(Path(args.out), args.n, args.seed, PrivacyEngine().store), indent=2))
        return 0

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


DEMO_PROMPTS = [
    "Draft an email to Sarah Chen (sarah.chen@northwind.io) confirming Northwind Capital's $1.2B offer for Project Falcon.",
    "Confidential: we're acquiring Meta's AR unit. List three risks to raise with Dr. Patel.",
    "My card 4111 1111 1111 1111 was double-charged by Globex Corp. Call me at (415) 555-0134. Write a dispute letter.",
    "What did Meta announce at Connect this year?",
]


def demo() -> int:
    import tempfile
    from pathlib import Path

    from .config import Settings
    from .pipeline import PrivacyEngine

    settings = Settings(home=Path(tempfile.mkdtemp(prefix="privacy-demo-")))
    engine = PrivacyEngine(settings)
    print(f"local detector: {', '.join(engine.protect('x').detection.backends)} · cloud: {engine.cloud.name}\n")
    for prompt in DEMO_PROMPTS:
        r = engine.ask(prompt)
        print(f"YOU   {prompt}\nCLOUD {r.protected.masked.masked}")
        print(f"BACK  {(r.answer or r.error).splitlines()[0]}\n")

    a = engine.audit()
    print(f"AUDIT scanned {a['requests_scanned']} requests / {a['bytes_scanned']} bytes for {a['secrets_checked']} "
          f"vault values: {'0 matches ✓' if a['clean'] else a['leaks']}")
    attack = engine.attempt_raw_send(DEMO_PROMPTS[0])
    print(f"ATTACK raw send {'refused ✓' if not attack['sent'] else 'SENT ✗'}: {attack['refused']}")
    return 0 if a["clean"] and not attack["sent"] else 1


def run_bench(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import bench
    from .cloud import CloudLLM
    from .config import Settings
    from .detector import Detector, LlamaDetector

    settings = Settings()
    llama = LlamaDetector(settings.local_llm_base_url, settings.local_llm_model) if args.llm else None
    if llama and not llama.available():
        print(f"local model {settings.local_llm_model} not reachable at {settings.local_llm_base_url}; using rules only")
        llama = None
    ask = None
    if args.online:
        cloud = CloudLLM(settings.cloud_base_url, settings.cloud_model, settings.cloud_api_key)
        if cloud.mock:
            print("--online needs CLOUD_API_KEY; skipping online scoring")
        else:
            ask = lambda text: cloud.complete([{"role": "user", "content": text}], {})  # noqa: E731
    report = bench.run(args.n, args.seed, use_llm=bool(llama), detector=Detector(llama), online=ask, online_n=args.online)
    print(bench.render(report))
    print(f"\nsaved {bench.save(report, Path('runs'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
