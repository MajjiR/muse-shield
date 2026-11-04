"""Compare recorded eval runs with paired bootstraps over the same documents.

    .venv/bin/python scripts/compare_models.py --nemotron base=full500-glimmer-base-rerun v2=full500-glimmer-v2 \
        --sectors v1c=sectors-glimmer-v1c v2=sectors-glimmer-v2 --baseline v1c --tag adapters

Each name=tag points at the newest results/<eval>/*_<tag>/ run.
- Nemotron: leak and core leak, recomputed per doc from the saved predictions.
- Sector test: entity F1 and context recall, from per_case counts. A case counts as all-missed
  when it is invalid or absent.

Differences vs --baseline are given with 95% CIs from 2,000 paired resamples of documents. The
output goes to results/model-comparison/<run>/ (comparison.md, comparison.json).
"""

from __future__ import annotations

import argparse
import glob
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield.benchmarks.nemotron import QUASI, Doc  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402
from muse_shield.sector_eval import load_cases  # noqa: E402

B = 2000


def run_dir(eval_name: str, tag: str) -> Path:
    hits = sorted(glob.glob(str(RESULTS / eval_name / f"*_{tag}")))
    if not hits:
        raise SystemExit(f"no {eval_name} run tagged {tag}")
    return Path(hits[-1])


def one_file(d: Path, suffix: str) -> Path:
    """The run's single backend file (glimmer.json, muse_spark.preds.jsonl, ...)."""
    hits = [p for p in d.glob(f"*{suffix}") if p.name != "manifest.json" and (suffix != ".json" or not p.name.endswith(".preds.json"))]
    if len(hits) != 1:
        raise SystemExit(f"expected one *{suffix} in {d}, found {[h.name for h in hits]}")
    return hits[0]


def nemotron_per_doc(tag: str, docs: dict[str, Doc]) -> dict[str, tuple[int, int, int, int]]:
    out = {}
    for line in one_file(run_dir("nemotron-pii", tag), ".preds.jsonl").read_text().splitlines():
        p = json.loads(line)
        doc = docs[p["uid"]]
        masked = {i for q in p["predictions"] for i in range(q["start"], q["end"])}
        g = l = cg = cl = 0
        for s in doc.spans:
            chars = set(range(s.start, s.end))
            leak = len(chars - masked)
            g += len(chars); l += leak
            if s.label not in QUASI:
                cg += len(chars); cl += leak
        out[p["uid"]] = (l, g, cl, cg)
    return out


def sector_per_case(tag: str, gold: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int, int, int, int]]:
    rep = json.loads(one_file(run_dir("sector-test", tag), ".json").read_text())
    rep = rep[0] if isinstance(rep, list) else rep
    if "per_case" not in rep:
        raise SystemExit(f"{tag} has no per_case counts (recorded before they were saved); rerun it")
    seen = {c["id"]: c for c in rep["per_case"]}
    out = {}
    for cid, (n_ent, n_ctx) in gold.items():
        c = seen.get(cid)
        if c and c.get("valid"):
            out[cid] = (c["tp"], c["fp"], c["fn"], c["ctx"][0], n_ctx)
        else:
            out[cid] = (0, 0, n_ent, 0, n_ctx)
    return out


def f1(rows) -> float:
    tp = sum(r[0] for r in rows); fp = sum(r[1] for r in rows); fn = sum(r[2] for r in rows)
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def ctx_recall(rows) -> float:
    tp = sum(r[3] for r in rows); n = sum(r[4] for r in rows)
    return tp / n if n else 0.0


def leak(rows) -> float:
    return sum(r[0] for r in rows) / max(1, sum(r[1] for r in rows))


def core_leak(rows) -> float:
    return sum(r[2] for r in rows) / max(1, sum(r[3] for r in rows))


def paired(a: dict, b: dict, metric, rng: random.Random) -> tuple[float, float, float]:
    keys = sorted(a)
    diff = metric([b[k] for k in keys]) - metric([a[k] for k in keys])
    ds = []
    for _ in range(B):
        s = [rng.choice(keys) for _ in keys]
        ds.append(metric([b[k] for k in s]) - metric([a[k] for k in s]))
    ds.sort()
    return diff, ds[int(0.025 * B)], ds[int(0.975 * B)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nemotron", nargs="*", default=[])
    ap.add_argument("--sectors", nargs="*", default=[])
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--nemotron-docs", type=Path, default=REPO.parents[1] / "runs/benchmarks/nemotron-test-500-s7.jsonl")
    ap.add_argument("--sector-dir", type=Path, default=REPO / "data/synth-v2/test")
    ap.add_argument("--tag", default="comparison")
    a = ap.parse_args(argv)
    rng = random.Random(0)
    md, js = [], {"baseline": a.baseline, "resamples": B, "nemotron": {}, "sectors": {}}

    def table(title, runs, metrics, lower_better):
        base = runs[a.baseline]
        md.append(f"## {title}\n\nDifference vs **{a.baseline}**, 95% CI from {B:,} paired resamples. "
                  f"{'Lower' if lower_better else 'Higher'} is better; * = CI excludes 0.\n")
        md.append("| model | " + " | ".join(m for m, _ in metrics) + " |")
        md.append("|---|" + "---|" * len(metrics))
        out = {}
        for name, rows in runs.items():
            cells, rec = [], {}
            for mname, fn in metrics:
                v = fn(list(rows.values()))
                rec[mname] = {"value": v}
                if name == a.baseline:
                    cells.append(f"{v:.1%}")
                    continue
                d, lo, hi = paired(base, rows, fn, rng)
                sig = "*" if lo > 0 or hi < 0 else ""
                rec[mname].update(diff=d, ci=[lo, hi])
                cells.append(f"{v:.1%} ({d:+.1%} [{lo:+.1%}, {hi:+.1%}]){sig}")
            out[name] = rec
            md.append(f"| {name} | " + " | ".join(cells) + " |")
        md.append("")
        return out

    if a.nemotron:
        docs = {d["uid"]: Doc.from_dict(d) for d in map(json.loads, a.nemotron_docs.read_text().splitlines())}
        runs = {n: nemotron_per_doc(t, docs) for n, t in (s.split("=", 1) for s in a.nemotron)}
        common = set.intersection(*(set(r) for r in runs.values()))
        runs = {n: {k: r[k] for k in common} for n, r in runs.items()}
        js["nemotron"] = table(f"Nemotron-PII ({len(common)} docs)", runs, [("leak", leak), ("core leak", core_leak)], True)
    if a.sectors:
        cases = load_cases(a.sector_dir)
        gold = {c.id: (len(c.entities), len(c.contexts)) for c in cases}
        runs = {n: sector_per_case(t, gold) for n, t in (s.split("=", 1) for s in a.sectors)}
        js["sectors"] = table(f"Sector test ({len(gold)} paragraphs)", runs, [("entity F1", f1), ("context recall", ctx_recall)], False)

    out = RESULTS / "model-comparison" / new_run_id(a.tag, time.time(), git_version())
    out.mkdir(parents=True, exist_ok=True)
    js["runs"] = {"nemotron": a.nemotron, "sectors": a.sectors}
    (out / "comparison.json").write_text(json.dumps(js, indent=2))
    (out / "comparison.md").write_text("# Model comparison\n\n" + "\n".join(md) + "\n")
    print("\n".join(md))
    print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
