"""Evaluate a backend against the synthetic labeled set.

    .venv/bin/python -m muse_shield.evals --backend glimmer --n 60

Metrics
  contract   valid JSON on first try, after the retry, retry rate
  entities   precision / recall / F1 on (text, type), overall and per type
  roles      accuracy of AMOUNT roles among correctly found amounts
  contexts   precision / recall on (kind, overlapping sentences); kind accuracy
  grounding  hallucinated spans: entities the model named that are not in the text
  cost       latency p50/p95, tokens, and dollars at the given per-token prices
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

from .analysis import Analysis
from .backends import Backend, BackendError, backend_from_env
from .evalset import Case, generate

# Fireworks serverless list price for muse-glimmer-30b, USD per 1M tokens (check before quoting).
DEFAULT_PRICE_IN, DEFAULT_PRICE_OUT = 0.35, 1.50


def _norm(s: str) -> str:
    return " ".join(s.casefold().split())


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def score_case(case: Case, a: Analysis) -> dict:
    gold = {(_norm(g.text), g.type): g for g in case.entities}
    pred: dict[tuple[str, str], str | None] = {}
    for s in a.entities:
        pred.setdefault((_norm(s.text), s.type), s.role)

    per_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    roles_ok = roles_total = 0
    for key in gold.keys() | pred.keys():
        t = key[1]
        if key in gold and key in pred:
            per_type[t][0] += 1
            if gold[key].role:
                roles_total += 1
                roles_ok += gold[key].role == pred[key]
        elif key in pred:
            per_type[t][1] += 1
        else:
            per_type[t][2] += 1

    # A predicted context matches a gold one if the kind agrees and the sentences overlap.
    used, ctx_tp, kind_ok = set(), 0, 0
    for c in a.contexts:
        for i, g in enumerate(case.contexts):
            if i not in used and set(c.sentences) & set(g.sentences):
                used.add(i)
                kind_ok += c.kind == g.kind
                ctx_tp += c.kind == g.kind
                break
    return {
        "per_type": dict(per_type),
        "roles": (roles_ok, roles_total),
        "contexts": (ctx_tp, len(a.contexts) - ctx_tp, len(case.contexts) - ctx_tp),
        "context_kind": (kind_ok, len(used)),
        "dropped": len(a.dropped),
    }


def run(backend: Backend, cases: list[Case], workers: int = 4,
        price_in: float = DEFAULT_PRICE_IN, price_out: float = DEFAULT_PRICE_OUT) -> dict:
    t0 = time.perf_counter()

    def one(case: Case):
        try:
            return case, backend.analyze([case.paragraph])[0], ""
        except BackendError as exc:
            return case, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, cases))

    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    roles = [0, 0]
    ctx = [0, 0, 0]
    kind = [0, 0]
    dropped = valid = first_try = errors = 0
    latencies, tokens_in, tokens_out = [], 0, 0
    failures = []
    by_template: dict[str, list[float]] = defaultdict(list)

    for case, a, err in results:
        if a is None:
            errors += 1
            failures.append({"id": case.id, "error": err})
            continue
        latencies.append(a.latency_ms)
        tokens_in += a.usage.get("prompt_tokens", 0)
        tokens_out += a.usage.get("completion_tokens", 0)
        if not a.valid:
            failures.append({"id": case.id, "error": a.error})
            continue
        valid += 1
        first_try += a.attempts == 1
        s = score_case(case, a)
        case_tp = case_fp = case_fn = 0
        for t, (tp, fp, fn) in s["per_type"].items():
            totals[t][0] += tp; totals[t][1] += fp; totals[t][2] += fn
            case_tp += tp; case_fp += fp; case_fn += fn
        by_template[case.template].append(_prf(case_tp, case_fp, case_fn)["f1"])
        roles[0] += s["roles"][0]; roles[1] += s["roles"][1]
        for i in range(3):
            ctx[i] += s["contexts"][i]
        kind[0] += s["context_kind"][0]; kind[1] += s["context_kind"][1]
        dropped += s["dropped"]
        if s["dropped"] or any(fp or fn for _, fp, fn in s["per_type"].values()):
            failures.append({"id": case.id, "template": case.template,
                             "missed": [e.text for e in case.entities if (_norm(e.text), e.type) not in {(_norm(x.text), x.type) for x in a.entities}],
                             "extra": sorted({x.text for x in a.entities if (_norm(x.text), x.type) not in {(_norm(e.text), e.type) for e in case.entities}}),
                             "hallucinated": [d["text"] for d in a.dropped]})

    n = len(cases)
    overall = _prf(*(sum(v[i] for v in totals.values()) for i in range(3)))
    lat = sorted(latencies)
    return {
        "backend": getattr(backend, "name", "?"),
        "model": getattr(backend, "model", "?"),
        "n": n,
        "seconds": round(time.perf_counter() - t0, 2),
        "contract": {"valid_rate": valid / n, "first_try_rate": first_try / n, "errors": errors},
        "entities": overall,
        "entities_by_type": {t: _prf(*v) for t, v in sorted(totals.items())},
        "role_accuracy": roles[0] / roles[1] if roles[1] else None,
        "contexts": _prf(*ctx),
        "context_kind_accuracy": kind[0] / kind[1] if kind[1] else None,
        "hallucinated_spans": dropped,
        "f1_by_template": {t: statistics.mean(v) for t, v in sorted(by_template.items())},
        "latency_ms": {"p50": lat[len(lat) // 2] if lat else None, "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None},
        "tokens": {"in": tokens_in, "out": tokens_out},
        "cost_usd": tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out,
        "failures": failures[:25],
    }


def render(r: dict) -> str:
    pct = lambda x: "–" if x is None else f"{x:.0%}"  # noqa: E731
    e, c = r["entities"], r["contexts"]
    lines = [
        f"# Eval: {r['backend']} · {r['model']}",
        "",
        f"n={r['n']} · {r['seconds']}s · cost ${r['cost_usd']:.4f} · tokens in/out {r['tokens']['in']}/{r['tokens']['out']}"
        f" · latency p50 {r['latency_ms']['p50'] or 0:.0f} ms, p95 {r['latency_ms']['p95'] or 0:.0f} ms",
        "",
        "| metric | value |", "|---|---|",
        f"| valid JSON (after retry) | {pct(r['contract']['valid_rate'])} |",
        f"| valid JSON first try | {pct(r['contract']['first_try_rate'])} |",
        f"| entity precision / recall / F1 | {pct(e['precision'])} / {pct(e['recall'])} / {pct(e['f1'])} |",
        f"| amount role accuracy | {pct(r['role_accuracy'])} |",
        f"| context precision / recall | {pct(c['precision'])} / {pct(c['recall'])} |",
        f"| context kind accuracy | {pct(r['context_kind_accuracy'])} |",
        f"| hallucinated spans (dropped) | {r['hallucinated_spans']} |",
        "", "| entity type | P | R | F1 |", "|---|---|---|---|",
    ]
    lines += [f"| {t} | {pct(m['precision'])} | {pct(m['recall'])} | {pct(m['f1'])} |" for t, m in r["entities_by_type"].items()]
    lines += ["", "| template | entity F1 |", "|---|---|"]
    lines += [f"| {t} | {pct(v)} |" for t, v in r["f1_by_template"].items()]
    return "\n".join(lines)


def _load_dotenv(path: Path = Path(".env")) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.evals")
    ap.add_argument("--backend", default=None, help="glimmer | muse_spark (default: ENGINE_BACKEND or glimmer)")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", type=Path, default=Path("runs/evals"))
    args = ap.parse_args(argv)

    _load_dotenv()
    try:
        backend = backend_from_env(args.backend)
    except BackendError as exc:
        print(f"cannot start backend: {exc}")
        return 2
    report = run(backend, generate(args.n, args.seed), workers=args.workers)
    print(render(report))
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (args.out / f"{report['backend']}-{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (args.out / f"{report['backend']}-{stamp}.md").write_text(render(report) + "\n")
    print(f"\nsaved {args.out}/{report['backend']}-{stamp}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
