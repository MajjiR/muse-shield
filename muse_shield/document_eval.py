"""Document eval: the 10 realistic examples as Word, PowerPoint and PDF files, masked by the real pipeline.

    .venv/bin/python -m muse_shield.document_eval --rounds 1 --tag docs10-spark

For every must-mask value: is it masked (a span covers it in the extracted text), and is it anywhere in
the masked copy (re-extracted)? Plus whether the copy passed the verifier, analysis calls, cost and time.
One extra "long" document (all 10 examples, about 10 pages) shows how packing cuts calls.
Made-up data only: analysis sends the raw text to Muse Spark.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter, defaultdict

from .app.engine import Masker
from .app.server import analyzer_from_env
from .app.vault import Vault
from .documents import samples
from .documents.pipeline import handler, mask_document
from .documents.text import MAX_UNIT_CHARS, build
from .documents.verify import _spaceless, norm, verify
from .realistic import EXAMPLES, Example, covered
from .results import git_version, save_run

FORMATS = ("docx", "pptx", "pdf")


def reextract(fmt: str, data: bytes) -> str:
    h = handler(fmt)
    doc = h.load(data)
    if fmt == "pdf":
        return "\n".join(p.get_text() for p in doc.doc)
    return build(h.blocks(doc)).text


def score_one(ex: Example, fmt: str, md, report) -> dict:
    out = reextract(fmt, md.data)
    out_n, out_s = norm(out), _spaceless(out)
    missed, leaked, lost = [], [], []
    for value, etype in ex.must:
        try:
            frac, _ = covered(md.doc_text.text, value, md.masked.spans)
        except ValueError:
            lost.append(value)  # not in the extracted text at all (an extraction problem, not a masking one)
            continue
        if frac < 0.5:
            missed.append({"value": value, "type": etype})
        if norm(value) in out_n or (len(_spaceless(value)) >= 6 and _spaceless(value) in out_s):
            leaked.append({"value": value, "type": etype})
    return {"id": ex.id, "format": fmt, "must": len(ex.must), "missed": missed, "leaked": leaked, "not_extracted": lost,
            "verified": report.ok, "failures": report.failures, "warnings": [w["code"] for w in md.warnings + report.warnings],
            "units": len(md.doc_text.units), "chars": len(md.doc_text.text), "cost_usd": md.masked.cost_usd or 0.0,
            "seconds": round(md.seconds, 2), "masked_text": md.masked.masked_text}


def run(rounds: int = 1, formats=FORMATS, unit_chars: int = MAX_UNIT_CHARS, long_doc: bool = True, analyzer=None) -> dict:
    analyzer = analyzer or analyzer_from_env()[0]
    if analyzer is None:
        raise SystemExit("analysis is off: " + analyzer_from_env()[1])
    examples = list(EXAMPLES)
    if long_doc:
        examples.append(Example("long-10", "All ten examples in one document",
                                "\n\n".join(e.text for e in EXAMPLES), [m for e in EXAMPLES for m in e.must]))
    rows = []
    t0 = time.perf_counter()
    for r in range(1, rounds + 1):
        for fmt in formats:
            for ex in examples:
                vault = Vault(":memory:", os.urandom(32))
                masker = Masker(vault, analyzer)
                data = samples.render(fmt, ex.text, [v for v, _ in ex.must])
                md = mask_document(data, masker, vault.create_chat(), max_unit_chars=unit_chars)
                row = score_one(ex, fmt, md, verify(md))
                row["round"] = r
                rows.append(row)
                print(f"round {r} · {fmt:4} · {ex.id:18} units {row['units']:3} · missed {len(row['missed'])}/{row['must']}"
                      f" · leaked {len(row['leaked'])} · {'verified' if row['verified'] else 'BLOCKED'}", flush=True)
    return {"rounds": rounds, "unit_chars": unit_chars, "seconds": round(time.perf_counter() - t0, 1),
            "model": getattr(analyzer, "model", "?"), "reasoning_effort": getattr(analyzer, "extra", {}).get("reasoning_effort"),
            "rows": rows}


def report_for(rep: dict, fmt: str) -> dict:
    rows = [r for r in rep["rows"] if r["format"] == fmt]
    must = sum(r["must"] for r in rows)
    missed = sum(len(r["missed"]) for r in rows)
    leaked = sum(len(r["leaked"]) for r in rows)
    by_type, by_type_missed = Counter(), Counter()
    for r in rows:
        for m in r["missed"]:
            by_type_missed[m["type"]] += 1
    consistent = defaultdict(int)
    for r in rows:
        for m in r["missed"]:
            consistent[(r["id"], m["value"])] += 1
    long_rows = [r for r in rows if r["id"] == "long-10"]
    return {"backend": f"muse_spark-{fmt}", "model": rep["model"], "docs": len(rows),
            "leak_rate": leaked / must if must else None, "span_recall": 1 - missed / must if must else None,
            "valid_rate": sum(r["verified"] for r in rows) / len(rows) if rows else None,
            "must_total": must, "missed_total": missed, "leaked_total": leaked,
            "not_extracted": sum(len(r["not_extracted"]) for r in rows),
            "missed_by_type": dict(by_type_missed), "consistent_misses": [
                {"id": k[0], "value": k[1], "times": v} for k, v in sorted(consistent.items(), key=lambda kv: -kv[1])],
            "units_per_doc": round(sum(r["units"] for r in rows) / len(rows), 1) if rows else None,
            "long_doc_units": long_rows[0]["units"] if long_rows else None,
            "warnings": dict(Counter(w for r in rows for w in r["warnings"])),
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 5), "cost": {"usd": round(sum(r["cost_usd"] for r in rows), 5), "basis": "tokens"},
            "seconds": round(sum(r["seconds"] for r in rows), 1)}


def render(rep: dict, reports: list[dict]) -> str:
    lines = [f"# Document eval: {rep['model']} (reasoning {rep['reasoning_effort']}), units up to {rep['unit_chars']} characters",
             "", "| format | docs | must values | masked | in the masked copy | copies verified | analysis calls / doc | long doc calls | cost |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        lines.append(f"| {r['backend'].split('-')[-1]} | {r['docs']} | {r['must_total']} | {r['span_recall']:.1%} | {r['leaked_total']} "
                     f"| {r['valid_rate']:.0%} | {r['units_per_doc']} | {r['long_doc_units']} | ${r['cost_usd']:.4f} |")
    lines += ["", "## Misses"]
    for r in reports:
        for m in r["consistent_misses"]:
            lines.append(f"- {r['backend']}: `{m['value']}` in {m['id']} ({m['times']}×)")
    if not any(r["consistent_misses"] for r in reports):
        lines.append("- none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.document_eval")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--unit-chars", type=int, default=MAX_UNIT_CHARS, help="analysis unit size; 0 = one unit per paragraph")
    ap.add_argument("--no-long", action="store_true", help="skip the 10-page combined document")
    ap.add_argument("--tag", default="docs10-spark")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args(argv)
    started, git = time.time(), git_version()
    rep = run(args.rounds, tuple(args.formats.split(",")), args.unit_chars, not args.no_long)
    reports = [report_for(rep, f) for f in args.formats.split(",")]
    md = render(rep, reports)
    print(md)
    if not args.no_record:
        out = save_run("document-pii", args.tag, reports, {r["backend"]: [x for x in rep["rows"] if x["format"] == r["backend"].split("-")[-1]] for r in reports},
                       settings={"model": rep["model"], "reasoning_effort": rep["reasoning_effort"], "rounds": rep["rounds"],
                                 "unit_chars": rep["unit_chars"], "contexts": False},
                       dataset={"name": "muse_shield.realistic rendered by muse_shield.documents.samples", "examples": len(EXAMPLES),
                                "long_doc": not args.no_long, "formats": args.formats.split(",")},
                       compare_md=md, when=started, git=git)
        print(f"recorded: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
