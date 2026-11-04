"""Consistent relabelling of weak quasi-identifiers in Nemotron training paragraphs.

    python -m muse_shield.relabel --test-sample <benchmark docs> --out runs/train/quasi-relabel-v2.jsonl

Nemotron labels job titles, employment status, education level and spoken language
inconsistently (e.g. "manager" labelled 17 times and left unlabelled 13). One Muse Spark
pass (Contributor mode: public data only) marks those four attributes in every training
paragraph with the same rule. trainset.nemotron_rows(quasi_map=...) then swaps them in for
Nemotron's own quasi labels. Output is appended per paragraph, so the pass is resumable.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .synth import spark
from .trainset import benchmark_paragraphs, nemotron_rows

PROMPT = """Find every span in the paragraph that states a specific person's:
- occupation or job title (e.g. "nurse", "Senior Data Analyst"),
- employment status (e.g. "full-time", "contractor", "retired", "terminated", "on medical leave"),
- education level or degree (e.g. "bachelor's degree", "PhD in Chemistry"),
- a language the person speaks (e.g. "Tamil", "fluent in Spanish" -> "Spanish").
Copy each span exactly as written. Do not include names, company names, departments or generic words.
If there are none, return an empty list.
Reply with JSON only: {{"spans": ["..."]}}

Paragraph:
{paragraph}"""


def load_map(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return {d["para_key"]: d["spans"] for d in map(json.loads, path.read_text().splitlines()) if "spans" in d}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.relabel")
    ap.add_argument("--test-sample", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("runs/train/quasi-relabel-v2.jsonl"))
    ap.add_argument("--n", type=int, default=4400)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--model", default="muse-spark-1.3-contributor")
    a = ap.parse_args(argv)
    os.environ.setdefault("META_SYNTHETIC_ONLY", "1")
    rows = nemotron_rows(a.n, a.seed, benchmark_paragraphs(a.test_sample), date_policy="specific")
    done = load_map(a.out)
    todo = [r["_meta"] for r in rows if r["_meta"]["para_key"] not in done]
    print(f"{len(rows)} paragraphs, {len(done)} already relabelled, {len(todo)} to go", flush=True)
    b = spark(a.model, "low", 4096)
    t0 = time.time()

    def work(meta: dict) -> dict:
        para = meta["paragraph"]
        try:
            raw, usage = b._call([{"role": "user", "content": PROMPT.format(paragraph=para)}])
            spans = [s.strip() for s in json.loads(raw).get("spans", []) if isinstance(s, str) and s.strip()]
        except Exception as exc:  # noqa: BLE001
            return {"para_key": meta["para_key"], "error": str(exc)[:200]}
        grounded = [s for s in dict.fromkeys(spans) if s in para]
        return {"para_key": meta["para_key"], "spans": grounded, "dropped_ungrounded": len(spans) - len(grounded), "usage": usage}

    a.out.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool, a.out.open("a") as f:
        for i, res in enumerate(pool.map(work, todo), 1):
            errors += "error" in res
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            if i % 200 == 0:
                print(f"{i}/{len(todo)} · {time.time() - t0:.0f}s · errors {errors}", flush=True)
    m = load_map(a.out)
    print(json.dumps({"paragraphs": len(rows), "relabelled": len(m), "with_spans": sum(bool(v) for v in m.values()),
                      "errors_this_run": errors, "seconds": round(time.time() - t0, 1)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
