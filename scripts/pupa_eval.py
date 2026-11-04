"""PUPA leak benchmark: how much private detail in real chatbot prompts would reach the cloud model.

    .venv/bin/python scripts/pupa_eval.py --n 120 --er <route> --pii <route> --spark

PUPA (Li et al., PAPILLON, NAACL 2025; Columbia-NLP/PUPA, MIT) is 901 real user prompts from WildChat, each
with `pii_units`: the private details in it. WildChat had already replaced names, phones, emails and URLs
with <PRESIDIO_ANONYMIZED_*> placeholders, so those units aren't real values and are skipped; what's left is
mostly companies, schools, places and other identifying details. Each prompt is masked exactly as the app
would (Masker: entities and, for paragraph models, context blocks), and a unit leaks if its text is still
in the masked prompt (case-insensitive). Leak rate = leaked units / units (lower is better).

Sample: English-looking prompts (ASCII), at most --max-chars long, with at least one real unit; a fixed
random sample of --n of them (seed 7), so every model sees the same prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import csv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield.app.engine import Masker  # noqa: E402
from muse_shield.app.vault import Vault  # noqa: E402
from muse_shield.backends import GlimmerBackend, MetaModelBackend  # noqa: E402
from muse_shield.config import load_env  # noqa: E402
from muse_shield.resolution import ResolutionAnalyzer  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402

SRC = Path("/Volumes/MajjiR/ai/datasets/pupa")
FW = "https://api.fireworks.ai/inference/v1"


def sample(n: int, max_chars: int, seed: int = 7) -> list[dict]:
    rows = []
    csv.field_size_limit(10**8)
    for f in ("PUPA_New.csv", "PUPA_TNB.csv"):
        with open(SRC / f, newline="", encoding="utf-8") as fh:
            records = list(csv.DictReader(fh))
        for r in records:
            q, units = r.get("user_query") or None, r.get("pii_units") or None
            if not isinstance(q, str) or not isinstance(units, str) or len(q) > max_chars:
                continue
            if sum(c.isascii() for c in q) / max(1, len(q)) < 0.97:
                continue
            real = [u.strip() for u in units.split("||") if u.strip() and "presidio_anonymized" not in u.lower()]  # incl. <...> forms
            real = [u for u in real if u.lower() in q.lower()]  # only units actually present in the prompt
            if real:
                rows.append({"id": f"{f.split('_')[1].split('.')[0].lower()}-{r['conversation_hash']}", "category": r["predicted_category"],
                             "query": q, "units": real})
    random.Random(seed).shuffle(rows)
    return rows[:n]


def run(name: str, analyzer, prompts: list[dict], workers: int) -> dict:
    vault = Vault(":memory:", os.urandom(32))
    masker = Masker(vault, analyzer)

    def one(p: dict) -> dict:
        t0 = time.perf_counter()
        try:
            m = masker.mask(p["query"], vault.create_chat())
            ok, masked, err = m.analysis_ok, m.masked_text, m.error
        except Exception as exc:  # noqa: BLE001 - a failed call leaks everything
            ok, masked, err = False, p["query"], f"{exc!s:.120}"
        if not ok:
            masked = p["query"]  # the app refuses to send on failure; scored as unprotected to be strict
        leaked = [u for u in p["units"] if u.lower() in masked.lower()]
        return {"id": p["id"], "category": p["category"], "units": p["units"], "leaked": leaked, "ok": ok, "error": err,
                "masked": masked, "seconds": round(time.perf_counter() - t0, 1)}

    t0 = time.time()
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(one, prompts))
    units = sum(len(r["units"]) for r in rows)
    leaked = sum(len(r["leaked"]) for r in rows)
    by_cat: dict[str, list[int]] = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], [0, 0])
        c[0] += len(r["leaked"])
        c[1] += len(r["units"])
    return {"name": name, "model": getattr(analyzer, "model", ""), "prompts": len(rows), "units": units,
            "leak_rate": leaked / max(1, units), "prompts_fully_protected": sum(not r["leaked"] for r in rows) / max(1, len(rows)),
            "valid": sum(r["ok"] for r in rows) / max(1, len(rows)), "seconds": round(time.time() - t0, 1),
            "by_category": {k: {"leak_rate": v[0] / v[1], "units": v[1]} for k, v in sorted(by_cat.items())}, "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--max-chars", type=int, default=3000)
    ap.add_argument("--er", default="", help="entity-resolution Glimmer route '<model>#<deployment>'")
    ap.add_argument("--pii", default="", help="stage-1 Glimmer route (PII + context)")
    ap.add_argument("--spark", action="store_true", help="also run cloud Muse Spark (public data only)")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--tag", default="pupa-sample")
    a = ap.parse_args(argv)
    load_env()
    prompts = sample(a.n, a.max_chars)
    started, git = time.time(), git_version()
    key = os.environ["FIREWORKS_API_KEY"]
    models = {}
    if a.er:
        models["Muse Glimmer + er-v2b (ours)"] = ResolutionAnalyzer(GlimmerBackend(FW, a.er, key, max_tokens=4000, timeout=300.0))
    if a.pii:
        models["Muse Glimmer + v2 (ours, PII + context)"] = GlimmerBackend(FW, a.pii, key, timeout=300.0)
    if a.spark:
        models["Muse Spark"] = MetaModelBackend(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), "muse-spark-1.3",
                                                os.environ.get("MODEL_API_KEY", ""), name="muse_spark", synthetic_only=True,
                                                reasoning_effort=os.environ.get("MUSE_SHIELD_ANALYSIS_EFFORT", "minimal"))
    print(f"PUPA sample: {len(prompts)} prompts, {sum(len(p['units']) for p in prompts)} real private details", flush=True)
    with ThreadPoolExecutor(len(models)) as pool:
        results = dict(zip(models, pool.map(lambda kv: run(kv[0], kv[1], prompts, a.workers), models.items())))
    out = RESULTS / "pupa" / new_run_id(a.tag, started, git)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# PUPA: private details from real chatbot prompts that would reach the cloud model", "",
             f"{len(prompts)} English prompts (seed 7, ≤{a.max_chars} chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat",
             "prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.", "",
             "| Model | Leak rate | Prompts fully protected | Valid | Time |", "|---|---|---|---|---|"]
    for name, r in results.items():
        lines.append(f"| {name} | **{r['leak_rate'] * 100:.1f}%** | {r['prompts_fully_protected'] * 100:.1f}% | "
                     f"{r['valid'] * 100:.0f}% | {r['seconds']:.0f}s |")
    cats = sorted({c for r in results.values() for c in r["by_category"]})
    lines += ["", "## Leak rate by category", "", "| Category | " + " | ".join(results) + " |", "|---|" + "---|" * len(results)]
    for c in cats:
        lines.append(f"| {c} | " + " | ".join(f"{r['by_category'].get(c, {}).get('leak_rate', 0) * 100:.1f}% "
                                              f"(n={r['by_category'].get(c, {}).get('units', 0)})" for r in results.values()) + " |")
    md = "\n".join(lines) + "\n"
    (out / "report.md").write_text(md)
    (out / "report.json").write_text(json.dumps({k: {x: y for x, y in v.items() if x != "rows"} for k, v in results.items()}, indent=1))
    for name, r in results.items():
        slug = "spark" if "Spark" in name else ("er-v2b" if "er-v2b" in name else "v2")
        (out / f"{slug}.rows.jsonl").write_text("".join(json.dumps({k: v for k, v in x.items() if k != "masked"}, ensure_ascii=False) + "\n"
                                                        for x in r["rows"]))
    (out / "manifest.json").write_text(json.dumps({"run_id": out.name, "eval": "pupa", "dataset": "Columbia-NLP/PUPA (PUPA_New.csv, PUPA_TNB.csv)",
                                                   "n": len(prompts), "max_chars": a.max_chars, "seed": 7,
                                                   "models": {k: v["model"] for k, v in results.items()}}, indent=1))
    print(md)
    print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
