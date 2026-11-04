"""Evaluate a backend on the held-out sector test documents (Spark-written, double-labelled, verified).

    .venv/bin/python -m muse_shield.sector_eval --backend glimmer --dir data/synth-v2/test --tag sectors-glimmer-base

Each test row becomes an eval Case (its numbered sentences, gold entities with roles, gold
contexts), so the same scoring as the synthetic contract eval applies: JSON validity, entity
P/R/F1 by type, amount-role accuracy, context P/R and kind accuracy, hallucinated spans, and
cost. `f1_by_template` reports per sector. Results are recorded in results/sector-test/.
Test documents were split off before labelling and never enter training.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from .backends import BackendError, backend_from_env
from .evals import render, run
from .evalset import Case, GoldContext, GoldEntity

_NUM = re.compile(r"\[(\d+)\] ")


def row_to_case(i: int, row: dict, meta: dict) -> Case:
    numbered = row["messages"][3]["content"].split("\n", 1)[1]
    parts = _NUM.split(numbered)
    sentences = [parts[k + 1].strip() for k in range(1, len(parts) - 1, 2)]
    gold = json.loads(row["messages"][-1]["content"])
    ents = [GoldEntity(e["text"], e["type"], e.get("role")) for e in gold["entities"]]
    ctxs = [GoldContext(c["sentences"], c["kind"]) for c in gold["contexts"]]
    return Case(f"t{i:05d}", meta.get("domain", "?"), sentences, ents, ctxs)


def load_cases(test_dir: Path, limit: int = 0) -> list[Case]:
    rows = [json.loads(l) for l in (test_dir / "rows.jsonl").read_text().splitlines() if l.strip()]
    metas = [json.loads(l) for l in (test_dir / "rows.manifest.jsonl").read_text().splitlines() if l.strip()]
    cases = [row_to_case(i, r, m) for i, (r, m) in enumerate(zip(rows, metas))]
    cases = [c for c in cases if c.sentences]
    return cases[:limit] if limit else cases


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.sector_eval")
    ap.add_argument("--backend", default=None, help="glimmer | muse_spark")
    ap.add_argument("--dir", type=Path, default=Path("data/synth-v2/test"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tag", default="sectors")
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args(argv)
    from .results import git_version, save_run

    try:
        backend = backend_from_env(a.backend)
    except BackendError as exc:
        print(f"cannot start backend: {exc}")
        return 2
    cases = load_cases(a.dir, a.limit)
    started, git_at_start = time.time(), git_version()
    report = run(backend, cases, workers=a.workers)
    print(render(report))
    if not a.no_record:
        summary = {**report, "span_recall": report["entities"]["recall"], "span_precision": report["entities"]["precision"],
                   "valid_rate": report["contract"]["valid_rate"], "docs": report["n"],
                   "recall_by_type": {t: m["recall"] for t, m in report["entities_by_type"].items()}}
        out = save_run("sector-test", a.tag, [summary], {}, compare_md=render(report),
                       settings={report["backend"]: {"model": report["model"], "workers": a.workers}},
                       dataset={"name": str(a.dir), "docs": len(cases)}, when=started, git=git_at_start)
        print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
