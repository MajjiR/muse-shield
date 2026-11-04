"""Run analysis backends on the Nemotron-PII sample and compare them.

    .venv/bin/python -m muse_shield.benchmarks.run --backends glimmer,muse_spark,muse_wonder --n 500
    .venv/bin/python -m muse_shield.benchmarks.run --backends glimmer --n 500 --limit 5   # smoke test

Documents are sent paragraph by paragraph, exactly as production will. The text goes
to each provider, which is fine for this public benchmark and nothing else.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..analysis import Analysis
from ..backends import Backend, BackendError, backend_from_env
from ..costs import deployment_info, run_cost
from ..results import git_version, save_run, sha256
from .nemotron import DATASET, LABEL_MAP, OUR_TYPES, QUASI, Doc, DocScore, load_or_sample, paragraphs, predictions, score

def analyze_doc(backend: Backend, doc: Doc) -> dict:
    t0 = time.perf_counter()
    analyses: list[tuple[int, Analysis]] = []
    errors = []
    for off, para in paragraphs(doc.text):
        try:
            analyses.append((off, backend.analyze([para])[0]))
        except BackendError as exc:
            errors.append(str(exc))
    return {"doc": doc, "analyses": analyses, "errors": errors, "latency_ms": (time.perf_counter() - t0) * 1000}


def aggregate(name: str, model: str, results: list[dict], seconds: float, gpu: dict | None = None) -> dict:
    total = DocScore()
    found_by_label: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    calls = valid = first_try = dropped = errors = 0
    tokens_in = tokens_out = tokens_cached = tokens_reasoning = 0
    latencies = []
    for r in results:
        doc, analyses = r["doc"], r["analyses"]
        errors += len(r["errors"])
        latencies.append(r["latency_ms"])
        for _, a in analyses:
            calls += 1
            valid += a.valid
            first_try += a.valid and a.attempts == 1
            dropped += len(a.dropped)
            tokens_in += a.usage.get("prompt_tokens", 0)
            tokens_out += a.usage.get("completion_tokens", 0)
            tokens_cached += a.usage.get("prompt_tokens_details.cached_tokens", 0)
            tokens_reasoning += a.usage.get("completion_tokens_details.reasoning_tokens", 0)
        s = score(doc, predictions(doc, analyses))
        for f in ("gold_chars", "leaked_chars", "core_gold_chars", "core_leaked_chars", "pred_total", "pred_on_gold", "type_ok", "type_checked"):
            setattr(total, f, getattr(total, f) + getattr(s, f))
        for label, (fd, tt) in s.gold_found.items():
            found_by_label[label][0] += fd
            found_by_label[label][1] += tt

    def rate(a, b):
        return a / b if b else None

    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for label, (fd, tt) in found_by_label.items():
        by_type[LABEL_MAP.get(label) or (label if label in OUR_TYPES else "OTHER")][0] += fd
        by_type[LABEL_MAP.get(label) or (label if label in OUR_TYPES else "OTHER")][1] += tt
    gold_found = sum(v[0] for v in found_by_label.values())
    gold_total = sum(v[1] for v in found_by_label.values())
    quasi_gold = total.gold_chars - total.core_gold_chars
    lat = sorted(latencies)
    tokens = {"in": tokens_in, "out": tokens_out, "cached_in": tokens_cached, "reasoning_out": tokens_reasoning}
    cost = run_cost(model, tokens, seconds, gpu)
    return {
        "backend": name, "model": model, "docs": len(results), "seconds": round(seconds, 1),
        "leak_rate": rate(total.leaked_chars, total.gold_chars),
        "core_leak_rate": rate(total.core_leaked_chars, total.core_gold_chars),
        "quasi_leak_rate": rate(total.leaked_chars - total.core_leaked_chars, quasi_gold),
        "span_recall": rate(gold_found, gold_total),
        "span_precision": rate(total.pred_on_gold, total.pred_total),
        "type_accuracy": rate(total.type_ok, total.type_checked),
        "recall_by_type": {t: rate(*v) for t, v in sorted(by_type.items())},
        "recall_by_label": {l: {"recall": rate(*v), "n": v[1]} for l, v in sorted(found_by_label.items())},
        "calls": calls, "valid_rate": rate(valid, calls), "first_try_rate": rate(first_try, calls),
        "hallucinated_spans": dropped, "errors": errors,
        "latency_ms_per_doc": {"p50": lat[len(lat) // 2] if lat else None,
                               "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None},
        "tokens": tokens,
        "cost_usd": cost["usd"], "cost": cost,
    }


def run_backend(backend: Backend, docs: list[Doc], workers: int = 8) -> tuple[dict, list[dict]]:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda d: analyze_doc(backend, d), docs))
    model = getattr(backend, "model", "?")
    gpu = deployment_info(model, getattr(backend, "api_key", "")) if "#" in model else None
    report = aggregate(backend.name, model, results, time.perf_counter() - t0, gpu)
    preds = [{"uid": r["doc"].uid, "errors": r["errors"],
              "predictions": [p.__dict__ for p in predictions(r["doc"], r["analyses"])],
              "invalid_calls": [a.error for _, a in r["analyses"] if not a.valid]} for r in results]
    return report, preds


def _pct(x) -> str:
    return "–" if x is None else f"{x:.1%}"


def render(reports: list[dict], n_docs: int) -> str:
    lines = [f"# Nemotron-PII benchmark · {n_docs} test docs", "",
             "Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers "
             f"({', '.join(sorted(QUASI))}).", "",
             "| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in reports:
        lat = r["latency_ms_per_doc"]
        basis = (r.get("cost") or {}).get("basis")
        cost = "–" if r["cost_usd"] is None else f"${r['cost_usd']:.2f}" + (" (GPU time)" if basis == "gpu_time" else "")
        lines.append(
            f"| {r['backend']} `{r['model']}` | {_pct(r['leak_rate'])} | {_pct(r['core_leak_rate'])} | {_pct(r['span_recall'])} | "
            f"{_pct(r['span_precision'])} | {_pct(r['type_accuracy'])} | {_pct(r['valid_rate'])} | {_pct(r['first_try_rate'])} | "
            f"{r['hallucinated_spans']} | {(lat['p50'] or 0) / 1000:.1f}s / {(lat['p95'] or 0) / 1000:.1f}s | "
            f"{r['tokens']['in']:,}/{r['tokens']['out']:,} | {cost} |")
    types = sorted({t for r in reports for t in r["recall_by_type"]})
    lines += ["", "## Recall by type", "", "| type | " + " | ".join(r["backend"] for r in reports) + " |",
              "|---" * (len(reports) + 1) + "|"]
    lines += [f"| {t} | " + " | ".join(_pct(r["recall_by_type"].get(t)) for r in reports) + " |" for t in types]
    labels = sorted({l for r in reports for l in r["recall_by_label"]})
    lines += ["", "## Recall by label", "", "| label | n | " + " | ".join(r["backend"] for r in reports) + " |",
              "|---" * (len(reports) + 2) + "|"]
    for l in labels:
        n = max(r["recall_by_label"].get(l, {}).get("n", 0) for r in reports)
        lines.append(f"| {l} | {n} | " + " | ".join(_pct(r["recall_by_label"].get(l, {}).get("recall")) for r in reports) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.benchmarks.run")
    ap.add_argument("--backends", default="glimmer", help="comma list: glimmer,muse_spark,muse_wonder")
    ap.add_argument("--n", type=int, default=500, help="sample size (cached)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0, help="only run the first K docs of the sample (smoke test)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=Path("runs/benchmarks"))
    ap.add_argument("--cache", type=Path, default=Path("runs/benchmarks"), help="where the sampled docs are cached")
    ap.add_argument("--tag", default="", help="label for the results registry (default: smoke or full)")
    ap.add_argument("--no-record", action="store_true", help="don't write to results/")
    ap.add_argument("--docs", type=Path, default=None,
                    help="another benchmark in the same span format (e.g. runs/eval/pii/gretel-finance-test.jsonl) instead of Nemotron")
    ap.add_argument("--eval-name", default="", help="results/<eval-name>/ for --docs (default pii-<file stem>)")
    args = ap.parse_args(argv)

    started, git_at_start = time.time(), git_version()  # the code that runs, even if the checkout changes later
    cache = args.docs or args.cache / f"nemotron-test-{args.n}-s{args.seed}.jsonl"
    docs = [Doc.from_dict(json.loads(l)) for l in cache.read_text().splitlines() if l.strip()] if args.docs \
        else load_or_sample(cache, args.n, args.seed)
    if args.limit:
        docs = docs[: args.limit]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = args.out / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    reports, all_preds, settings = [], {}, {}
    for name in [b.strip() for b in args.backends.split(",") if b.strip()]:
        try:
            backend = backend_from_env(name)
        except BackendError as exc:
            print(f"skip {name}: {exc}")
            continue
        print(f"running {name} ({backend.model}) on {len(docs)} docs …", flush=True)
        report, preds = run_backend(backend, docs, args.workers)
        reports.append(report)
        all_preds[name] = preds
        settings[name] = {"model": backend.model, "workers": args.workers, "max_tokens": getattr(backend, "max_tokens", None),
                          "json_mode": getattr(backend, "json_mode", None), **getattr(backend, "extra", {})}
        (run_dir / f"{name}.json").write_text(json.dumps(report, indent=2))
        (run_dir / f"{name}.preds.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds))
        print(f"  leak {_pct(report['leak_rate'])} · recall {_pct(report['span_recall'])} · valid {_pct(report['valid_rate'])} "
              f"· errors {report['errors']} · {report['seconds']}s", flush=True)
    if not reports:
        return 2
    md = render(reports, len(docs))
    (run_dir / "compare.md").write_text(md + "\n")
    print("\n" + md + f"\n\nsaved {run_dir}/")
    if not args.no_record:
        dataset = {"name": str(args.docs) if args.docs else DATASET, "split": "test", "docs": len(docs), "sample_n": args.n,
                   "seed": args.seed, "limit": args.limit, "sample_file": cache.name, "sample_sha256": sha256(cache),
                   "task": os.environ.get("ANALYSIS_TASK", "full")}
        out = save_run(args.eval_name or (f"pii-{args.docs.stem}" if args.docs else "nemotron-pii"), args.tag or ("smoke" if args.limit else "full"), reports, all_preds,
                       settings=settings, dataset=dataset, compare_md=md, when=started, git=git_at_start)
        print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
