"""Labeller bake-off: which model should label training data? Scored only against known answers.

    .venv/bin/python scripts/labeler_bakeoff.py --nemotron-docs 60 --planted-docs 50 \
        spark-low=muse-spark-1.3-contributor:low spark-medium=muse-spark-1.3-contributor:medium wonder-low=muse-wonder-1.0:low

Each labeller runs the app's analysis prompt on the same text.
- Part A: Nemotron-PII *train* documents (labels by construction; never in our benchmark). It reports
  leak, core leak, recall, precision, valid JSON, tokens and cost, plus which gold spans each labeller
  missed. That shows how often two labellers miss the *same* span, i.e. whether a second opinion adds anything.
- Part B: held-out sector documents with code-planted values. It reports the share of planted names,
  phones, emails and IDs each labeller left unlabelled.
Raw text goes to the Meta Model API, so only this public/synthetic data is used (META_SYNTHETIC_ONLY).
The output goes to results/labeler-bakeoff/<run>/ (bakeoff.md, bakeoff.json, per-labeller predictions).
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield.benchmarks import nemotron  # noqa: E402
from muse_shield.benchmarks.nemotron import QUASI, paragraphs, predictions  # noqa: E402
from muse_shield.benchmarks.run import aggregate, analyze_doc  # noqa: E402
from muse_shield.config import load_env  # noqa: E402
from muse_shield.costs import run_cost  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402
import threading  # noqa: E402

from muse_shield.backends import AzureFoundryBackend, DeepSeekBackend  # noqa: E402
from muse_shield.synth import PACK_VALUE_KEYS, _CappedSpark  # noqa: E402

AZURE_SLOTS = threading.BoundedSemaphore(int(os.environ.get("AZURE_CONCURRENCY", "8")))


class _CappedAzure(AzureFoundryBackend):
    def _call(self, messages):
        with AZURE_SLOTS:
            return super()._call(messages)


DEEPSEEK_SLOTS = threading.BoundedSemaphore(int(os.environ.get("DEEPSEEK_CONCURRENCY", "32")))


class _CappedDeepSeek(DeepSeekBackend):
    def _call(self, messages):
        with DEEPSEEK_SLOTS:
            return super()._call(messages)

TRAIN_ROWS = 50_000


def labeller(name: str, spec: str):
    if spec.startswith("deepseek:"):  # deepseek:<model id from the DeepSeek API>
        b = _CappedDeepSeek(spec.split(":", 1)[1])
        b.name = name
        return b
    if spec.startswith("azure:"):  # azure:<Foundry deployment name>
        b = _CappedAzure(spec.split(":", 1)[1])
        b.name = name
        return b
    model, effort = spec.rsplit(":", 1)
    return _CappedSpark(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), model, os.environ["MODEL_API_KEY"],
                        name=name, synthetic_only=True, reasoning_effort=effort, max_tokens=8192)


def nemotron_train_docs(n: int, seed: int) -> list:
    rng = random.Random(seed)
    offs = rng.sample(range(0, TRAIN_ROWS - 100, 100), max(2, n // 40 + 1))
    pool = [nemotron.parse_row(r) for o in offs for r in nemotron._fetch_page(o, split="train")]
    rng.shuffle(pool)
    return pool[:n]


def planted_docs(n: int, seed: int) -> list[dict]:
    docs = [json.loads(l) for l in (REPO / "data/synth-v2/test/docs.jsonl").read_text().splitlines() if l.strip()]
    random.Random(seed).shuffle(docs)
    by_sector: dict[str, list] = {}
    for d in docs:
        by_sector.setdefault(d["sector"], []).append(d)
    picked = [d for group in itertools.zip_longest(*by_sector.values()) for d in group if d]  # round-robin sectors
    return picked[:n]


def gold_hits(doc, analyses) -> dict[tuple, bool]:
    """Per non-quasi gold span: was at least half of it masked?"""
    masked = {i for p in predictions(doc, analyses) for i in range(p.start, p.end)}
    return {(doc.uid, g.start, g.end): len(set(range(g.start, g.end)) & masked) * 2 >= g.end - g.start
            for g in doc.spans if g.label not in QUASI}


def planted_part(backend, docs: list[dict], workers: int) -> dict:
    def one(doc):
        out = []
        for _, para in paragraphs(doc["text"]):
            try:
                a = backend.analyze_one(para)
            except Exception as exc:  # noqa: BLE001  one throttled call must not sink the run
                out.append({"valid": False, "present": [], "missed": [], "usage": {}, "error": str(exc)[:160]})
                continue
            values = [doc["pack"][k] for k in PACK_VALUE_KEYS] + list(doc["pack"].get("people", []))
            present = [v for v in values if v and v in para]
            ents = [{"text": e.text, "type": e.type} for e in a.entities] if a.valid else []
            missed = [v for v in present if not any(v in e["text"] or (e["text"] in v and len(e["text"]) >= 4) for e in ents)]
            out.append({"valid": a.valid, "present": present, "missed": missed, "usage": a.usage})
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [r for doc_rows in pool.map(one, docs) for r in doc_rows]
    present = sum(len(r["present"]) for r in rows)
    missed = sum(len(r["missed"]) for r in rows)
    return {"paragraphs": len(rows), "invalid": sum(not r["valid"] for r in rows), "errors": sum("error" in r for r in rows),
            "planted": present, "missed": missed,
            "planted_recall": 1 - missed / present if present else None,
            "missed_examples": [v for r in rows for v in r["missed"]][:20],
            "tokens_in": sum(r["usage"].get("prompt_tokens", 0) for r in rows),
            "tokens_out": sum(r["usage"].get("completion_tokens", 0) for r in rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("labellers", nargs="+", help="name=model:effort (Meta Model API) or name=azure:<deployment>")
    ap.add_argument("--nemotron-docs", type=int, default=60)
    ap.add_argument("--planted-docs", type=int, default=50)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--tag", default="bakeoff")
    ap.add_argument("--part-a-preds", type=Path, default=None,
                    help="re-score part A from <dir>/<name>.preds.jsonl of an earlier run instead of calling the models again")
    a = ap.parse_args(argv)
    load_env()
    os.environ["META_SYNTHETIC_ONLY"] = "1"
    started, git = time.time(), git_version()
    ndocs = nemotron_train_docs(a.nemotron_docs, a.seed) if a.nemotron_docs else []
    pdocs = planted_docs(a.planted_docs, a.seed) if a.planted_docs else []
    print(f"{len(ndocs)} Nemotron train docs ({sum(len(paragraphs(d.text)) for d in ndocs)} paragraphs), "
          f"{len(pdocs)} planted docs", flush=True)
    specs = dict(s.split("=", 1) for s in a.labellers)
    out = RESULTS / "labeler-bakeoff" / new_run_id(a.tag, started, git)
    out.mkdir(parents=True, exist_ok=True)
    reports, hits = {}, {}

    def rescored(name):
        """Part A from saved predictions: leak/recall only (tokens and JSON validity were not saved)."""
        from muse_shield.benchmarks.nemotron import LABEL_MAP, DocScore, Pred, score
        by_uid = {d.uid: d for d in ndocs}
        total, found, h = DocScore(), collections.defaultdict(lambda: [0, 0]), {}
        for line in (a.part_a_preds / f"{name}.preds.jsonl").read_text().splitlines():
            p = json.loads(line)
            doc = by_uid[p["uid"]]
            preds = [Pred(**x) for x in p["predictions"]]
            s = score(doc, preds)
            for f in ("gold_chars", "leaked_chars", "core_gold_chars", "core_leaked_chars", "pred_total", "pred_on_gold"):
                setattr(total, f, getattr(total, f) + getattr(s, f))
            for label, (fd, tt) in s.gold_found.items():
                t_ = LABEL_MAP.get(label, "OTHER")
                found[t_][0] += fd
                found[t_][1] += tt
            masked = {i for q in preds for i in range(q.start, q.end)}
            h.update({(doc.uid, g.start, g.end): len(set(range(g.start, g.end)) & masked) * 2 >= g.end - g.start
                      for g in doc.spans if g.label not in QUASI})
        r = lambda x, y: x / y if y else None  # noqa: E731
        return {"leak_rate": r(total.leaked_chars, total.gold_chars), "core_leak_rate": r(total.core_leaked_chars, total.core_gold_chars),
                "span_recall": r(sum(v[0] for v in found.values()), sum(v[1] for v in found.values())),
                "span_precision": r(total.pred_on_gold, total.pred_total), "valid_rate": None, "tokens": {}, "calls": 0,
                "cost_usd": 0, "recall_by_type": {t_: r(*v) for t_, v in sorted(found.items())}, "rescored_from": str(a.part_a_preds)}, h

    def run_one(name):
        b = labeller(name, specs[name])
        t0 = time.perf_counter()
        if a.part_a_preds:
            rep, h = rescored(name)
            results = []
        else:
            with ThreadPoolExecutor(max_workers=a.workers) as pool:
                results = list(pool.map(lambda d: analyze_doc(b, d), ndocs))
            rep = aggregate(name, b.model, results, time.perf_counter() - t0) if ndocs else {}
            h = {}
            for r in results:
                h.update(gold_hits(r["doc"], r["analyses"]))
        if results:
            (out / f"{name}.preds.jsonl").write_text("".join(json.dumps({"uid": r["doc"].uid, "predictions": [p.__dict__ for p in predictions(r["doc"], r["analyses"])]}) + "\n" for r in results))
        rep["planted"] = planted_part(b, pdocs, a.workers) if pdocs else None
        if rep["planted"]:  # cached input isn't tracked in part B, so this is an upper bound
            rep["planted"]["cost_usd"] = run_cost(b.model, {"in": rep["planted"]["tokens_in"], "out": rep["planted"]["tokens_out"], "cached_in": 0}, 0)["usd"]
        print(f"{name}: done in {time.perf_counter() - t0:.0f}s", flush=True)
        return name, rep, h

    with ThreadPoolExecutor(max_workers=len(specs)) as pool:  # labellers in parallel; the global cap limits calls
        for name, rep, h in pool.map(run_one, specs):
            reports[name], hits[name] = rep, h

    names = list(specs)
    pct = lambda x: "–" if x is None else f"{x:.1%}"  # noqa: E731
    md = [f"# Labeller bake-off\n\nPart A: {len(ndocs)} Nemotron-PII train documents (labels by construction). "
          f"Part B: {len(pdocs)} held-out sector documents with code-planted values.\n",
          "| labeller | leak ↓ | core leak ↓ | span recall | precision | valid JSON | planted missed ↓ | reasoning tokens/call | cost |",
          "|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        r, p = reports[n], reports[n]["planted"] or {}
        calls = (r.get("calls") or 0) + (p.get("paragraphs") or 0)
        cost = (r.get("cost_usd") or 0) + (p.get("cost_usd") or 0)
        md.append(f"| {n} (`{specs[n]}`) | {pct(r.get('leak_rate'))} | {pct(r.get('core_leak_rate'))} | {pct(r.get('span_recall'))} | "
                  f"{pct(r.get('span_precision'))} | {pct(r.get('valid_rate'))} | {p.get('missed', '–')}/{p.get('planted', '–')} "
                  f"({pct(1 - p['planted_recall']) if p.get('planted_recall') is not None else '–'}) | "
                  f"{(r.get('tokens', {}).get('reasoning_out', 0) // max(1, r.get('calls') or 1))} | ${cost:.3f} |")
    md += ["", "## Shared misses on Nemotron core spans\n",
           "Gold (non-quasi) spans missed by one labeller, and how many of those the other also missed. A high "
           "share means a second opinion from that labeller adds little.\n", "| A missed | n | also missed by B | share |", "|---|---|---|---|"]
    shared = {}
    for x, y in itertools.permutations(names, 2):
        keys = hits[x].keys() & hits[y].keys()
        mx = [k for k in keys if not hits[x][k]]
        both = [k for k in mx if not hits[y][k]]
        shared[f"{x}|{y}"] = {"missed_by_a": len(mx), "also_b": len(both)}
        md.append(f"| {x} → {y} | {len(mx)} | {len(both)} | {len(both) / len(mx):.0%} |" if mx else f"| {x} → {y} | 0 | 0 | – |")
    keys = set.intersection(*(set(h) for h in hits.values())) if hits else set()
    all_miss = sum(all(not hits[n][k] for n in names) for k in keys)
    md.append(f"\nCore gold spans: {len(keys)}; missed by every labeller: {all_miss} ({all_miss / max(1, len(keys)):.1%}).")
    for n in names:
        md += ["", f"**{n}** recall by type: " + ", ".join(f"{t} {v:.0%}" for t, v in (reports[n].get("recall_by_type") or {}).items() if v is not None)]
        if reports[n]["planted"]:
            md.append(f"planted values missed (examples): {reports[n]['planted']['missed_examples'][:10]}")
    (out / "bakeoff.md").write_text("\n".join(md) + "\n")
    (out / "bakeoff.json").write_text(json.dumps({"labellers": specs, "reports": reports, "shared_misses": shared,
                                                  "core_spans": len(keys), "missed_by_all": all_miss,
                                                  "git": git, "seed": a.seed}, indent=2, default=str))
    print("\n".join(md))
    print(f"\nrecorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
