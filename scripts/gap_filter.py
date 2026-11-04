"""Drop training rows whose gold labels likely miss core PII, using Muse Spark (Contributor) as a second opinion.

    .venv/bin/python scripts/gap_filter.py runs/train/pii-v1 --sources gretel-finance

For each row from the given sources, Spark labels the paragraph with the stage-1 prompt. If it finds an
ID, CONTACT, SECRET, ADDRESS or PERSON that no gold label covers, the row is dropped; Spark's labels are
never added. That way a Spark mistake can only cost a row, not teach a wrong label. Rows from other
sources pass through. Writes train.jsonl / train.manifest.jsonl in place (originals kept as *.unfiltered)
and gaps.jsonl with every dropped row and the spans Spark found. Public/synthetic data only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from muse_shield.config import load_env  # noqa: E402
from muse_shield.synth import _CappedSpark  # noqa: E402

CORE = {"ID", "CONTACT", "SECRET", "ADDRESS", "PERSON"}


def paragraph_of(row: dict) -> str:
    return " ".join(s.split("] ", 1)[1] if "] " in s else s for s in re.split(r" (?=\[\d+\] )", row["messages"][3]["content"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", type=Path)
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args(argv)
    load_env()
    os.environ["META_SYNTHETIC_ONLY"] = "1"
    rows = [json.loads(l) for l in (a.dir / "train.jsonl").read_text().splitlines()]
    man = [json.loads(l) for l in (a.dir / "train.manifest.jsonl").read_text().splitlines()]
    b = _CappedSpark(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), "muse-spark-1.3-contributor", os.environ["MODEL_API_KEY"],
                     name="gap", synthetic_only=True, reasoning_effort="low", max_tokens=8192)
    b.task = "pii"

    def check(i: int):
        gold = json.loads(rows[i]["messages"][-1]["content"])["entities"]
        try:
            res = b.analyze_one(paragraph_of(rows[i]))
        except Exception as exc:  # noqa: BLE001
            return i, None, str(exc)[:120]
        if not res.valid:
            return i, None, "invalid"
        g = " ".join(e["text"] for e in gold)
        extra = sorted({(s.text, s.type) for s in res.entities if s.type in CORE and s.text not in g
                        and not any(s.text in e["text"] or e["text"] in s.text for e in gold)})
        return i, extra, ""

    todo = [i for i, m in enumerate(man) if m["source"] in a.sources]
    print(f"checking {len(todo)} rows from {a.sources}", flush=True)
    flagged, errors, done = {}, 0, 0
    with ThreadPoolExecutor(a.workers) as pool:
        for i, extra, err in pool.map(check, todo):
            done += 1
            errors += bool(err)
            if extra:
                flagged[i] = extra
            if done % 500 == 0:
                print(f"{done}/{len(todo)} checked, {len(flagged)} flagged, {errors} errors", flush=True)
    for name in ("train.jsonl", "train.manifest.jsonl"):
        shutil.copy(a.dir / name, a.dir / f"{name}.unfiltered")
    keep = [i for i in range(len(rows)) if i not in flagged]
    (a.dir / "train.jsonl").write_text("".join(json.dumps(rows[i], ensure_ascii=False) + "\n" for i in keep))
    (a.dir / "train.manifest.jsonl").write_text("".join(json.dumps(man[i], ensure_ascii=False) + "\n" for i in keep))
    (a.dir / "gaps.jsonl").write_text("".join(json.dumps({"row": i, "source": man[i]["source"], "spark_found": flagged[i]}, ensure_ascii=False) + "\n" for i in sorted(flagged)))
    stats = json.loads((a.dir / "stats.json").read_text())
    stats["gap_filter"] = {"sources": a.sources, "checked": len(todo), "dropped": len(flagged), "errors": errors, "kept_total": len(keep)}
    (a.dir / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats["gap_filter"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
