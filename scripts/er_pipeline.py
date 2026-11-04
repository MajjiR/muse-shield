"""Prompt-only test of the multi-step masking pipeline on the current entity-resolution model (no training).

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_pipeline.py muse-shield-glimmer-er-v2b --tag pipeline-v2b

Steps, every call on the same fine-tuned Glimmer deployment (created here, deleted in a `finally`):
1. classify: a new prompt asks for the document's categories and a one-line summary. For comparison,
   categories are also derived in code from the entities step 2 finds.
2. fill: the model's own resolution prompt -> entities, owners, relations -> masked text.
3. paragraph check: each masked paragraph goes back through the resolution prompt; anything it finds
   outside the placeholders (and that isn't a pronoun) is masked as a fallback.

Scored on the workflow examples (outputs only) and on samples of the test, challenge and ambiguity
sets: leaks before and after the paragraph check, fallback false alarms, category accuracy, calls, time.
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

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "scripts")]

from fireworks import Fireworks  # noqa: E402

from eval_adapters import ACCOUNT, load_env, log, shape_for, wait_serving  # noqa: E402
from muse_shield import resolution as R  # noqa: E402
from muse_shield.analysis import ContractError, _loads  # noqa: E402
from muse_shield.backends import GlimmerBackend  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402

CATEGORIES = ["medical", "legal", "mergers_acquisitions", "banking_finance", "hr", "insurance", "real_estate",
              "education", "code", "general"]
CLASSIFY_PROMPT = """Classify this document for a privacy gateway. Categories: {cats}.
A document can have more than one. Return ONE JSON object and nothing else:
{{"categories": ["..."], "summary": "one sentence about what the document is"}}

{doc}"""
# expected categories for the generated families (what the test sets know about each document)
FAMILY_CATS = {
    "hr_compensation": {"hr"}, "payroll_table": {"hr"}, "hr_investigation": {"hr"}, "us_onboarding": {"hr"},
    "relocation_letter": {"hr"}, "team_review": {"hr"}, "meeting_minutes": {"general", "hr"},
    "email_thread": {"general"}, "loan_sanction": {"banking_finance"}, "kyc_update": {"banking_finance"},
    "loan_guarantors": {"banking_finance"}, "medical_referral": {"medical"}, "minor_consent": {"medical"},
    "insurance_claim": {"insurance"}, "family_insurance": {"insurance"}, "legal_notice": {"legal"},
    "sibling_estate": {"legal"}, "ma_memo": {"mergers_acquisitions"}, "tenancy_agreement": {"real_estate", "legal"},
    "school_admission": {"education"}, "passport_minor": {"general", "legal"}, "generic": {"general"},
}
SECTOR_CATS = {"HR": {"hr"}, "Banking": {"banking_finance"}, "Healthcare": {"medical"}, "Legal": {"legal"},
               "M&A": {"mergers_acquisitions"}, "Insurance": {"insurance"}, "Real estate": {"real_estate"},
               "Education": {"education"}, "US HR": {"hr"}, "Payroll": {"hr"}}


def categories_from_entities(res: R.Resolution) -> set[str]:
    """Step 1 without a prompt: infer categories from what the model found."""
    subs = {e.subtype for e in res.entities if e.subtype}
    roles = {e.role for e in res.entities if e.role}
    rels = {r for _, r, _ in res.relations}
    types = {e.type for e in res.entities}
    cats = set()
    if subs & {"HEALTH", "MEDICAL_RECORD", "BODY_MEASUREMENT", "DISABILITY"} or "TREATS" in rels:
        cats.add("medical")
    if roles & {"SALARY"} or subs & {"EMPLOYEE_ID"} or "MANAGES" in rels:
        cats.add("hr")
    if roles & {"DEAL_VALUE", "REVENUE"} or "PROJECT" in types:
        cats.add("mergers_acquisitions")
    if roles & {"LOAN"} or subs & {"BANK_ACCOUNT", "IFSC", "CARD"} or "GUARANTOR_FOR" in rels:
        cats.add("banking_finance")
    if subs & {"POLICY"} or "NOMINEE_OF" in rels:
        cats.add("insurance")
    if rels & {"REPRESENTS", "CLIENT_OF"}:
        cats.add("legal")
    if "LANDLORD_OF" in rels:
        cats.add("real_estate")
    if "SECRET" in types:
        cats.add("code")
    return cats or {"general"}


def masked_with_map(res: R.Resolution) -> tuple[str, list[tuple[int, int, int]]]:
    """Masked text plus (masked_start, masked_end, original_start) for every stretch of unchanged text."""
    out = R.mask(res)
    spans = sorted(((m.start, m.end) for e in res.entities for m in e.mentions if not m.reference), key=lambda x: (x[0], -x[1]))
    kept, cursor = [], 0
    for s, e in spans:
        if s < cursor:
            continue
        kept.append((cursor, s))
        cursor = e
    kept.append((cursor, len(res.text)))
    # walk the masked text: unchanged stretches appear in order, separated by placeholders
    segs, pos = [], 0
    masked = out["masked"]
    for a, b in kept:
        piece = res.text[a:b]
        i = masked.find(piece, pos) if piece else pos
        if i < 0:
            continue
        segs.append((i, i + len(piece), a))
        pos = i + len(piece)
    return masked, segs


def to_original(segs, s: int, e: int) -> tuple[int, int] | None:
    for ms, me, os_ in segs:
        if ms <= s and e <= me:
            return os_ + (s - ms), os_ + (e - ms)
    return None


def call_json(backend, messages, retries: int = 1) -> tuple[dict | None, str]:
    raw = ""
    for _ in range(retries + 1):
        try:
            raw, _ = backend._call(messages)
            return _loads(raw), raw
        except ContractError:
            continue
    return None, raw


def run_doc(backend, doc: dict) -> dict:
    text, t0, calls = doc["text"], time.perf_counter(), 0
    # 1. classify by prompt
    data, raw_cls = call_json(backend, [{"role": "user", "content": CLASSIFY_PROMPT.format(cats=", ".join(CATEGORIES), doc=text)}])
    calls += 1
    prompt_cats = None
    if data and isinstance(data.get("categories"), list):
        prompt_cats = {str(c).lower() for c in data["categories"]} & set(CATEGORIES)
    # 2. fill with the model's own prompt
    res, err = None, ""
    try:
        raw, _ = backend._call(R.messages(text, example=False))
        calls += 1
        res = R.parse(raw, text)
    except Exception as exc:  # noqa: BLE001
        err = f"{exc!s:.100}"
    if res is None:
        return {"uid": doc.get("uid") or doc.get("id"), "error": err, "calls": calls}
    rule_cats = categories_from_entities(res)
    masked, segs = masked_with_map(res)
    # 3. paragraph check on the masked text
    fallback = []
    paras, pos = [], 0
    for block in masked.split("\n\n"):
        paras.append((pos, block))
        pos += len(block) + 2
    for p0, block in paras:
        plain = block
        if not plain.strip() or not any(ch.isalpha() for ch in plain.replace("<", "").replace(">", "")):
            continue
        try:
            raw2, _ = backend._call(R.messages(plain, example=False))
            calls += 1
            res2 = R.parse(raw2, plain)
        except Exception:  # noqa: BLE001
            continue
        for e in res2.entities:
            for m in e.mentions:
                if m.reference or "<" in m.text or ">" in m.text:
                    continue
                orig = to_original(segs, p0 + m.start, p0 + m.end)
                if orig:
                    fallback.append({"start": orig[0], "end": orig[1], "text": text[orig[0]:orig[1]], "type": e.type})
    return {"uid": doc.get("uid") or doc.get("id"), "family": doc.get("family"), "sector": doc.get("sector"),
            "prompt_categories": sorted(prompt_cats) if prompt_cats is not None else None, "raw_classify": raw_cls[:300],
            "summary": (data or {}).get("summary"), "rule_categories": sorted(rule_cats), "masked": masked,
            "fallback": fallback, "calls": calls, "seconds": round(time.perf_counter() - t0, 1),
            "pred": {"entities": [{"id": e.id, "type": e.type, "role": e.role, "subtype": e.subtype, "owner": e.owner,
                                   "mentions": [[m.start, m.end] for m in e.mentions]} for e in res.entities],
                     "relations": [list(r) for r in res.relations]}}


def leak_stats(gold: dict, row: dict) -> dict:
    """Leaks with the model's masks, then with the fallback added; fallback spans outside every gold mention."""
    text = gold["text"]
    cov1 = [False] * len(text)
    for e in row["pred"]["entities"]:
        for s, t in e["mentions"]:
            if not (R.is_reference(text[s:t]) and e["type"] in ("PERSON", "ORG")):
                for i in range(s, t):
                    cov1[i] = True
    cov2 = list(cov1)
    for f in row["fallback"]:
        for i in range(f["start"], f["end"]):
            cov2[i] = True
    out = {"total": 0, "leak_before": 0, "leak_after": 0, "fallback": len(row["fallback"]), "fallback_false": 0}
    gold_spans = []
    for e in gold["entities"]:
        for s, t in e["mentions"]:
            gold_spans.append((s, t))
            if R.is_reference(text[s:t]) and e["type"] in ("PERSON", "ORG"):
                continue
            out["total"] += 1
            out["leak_before"] += not all(cov1[i] for i in range(s, t) if text[i].isalnum())
            out["leak_after"] += not all(cov2[i] for i in range(s, t) if text[i].isalnum())
    for f in row["fallback"]:
        out["fallback_false"] += not any(s < f["end"] and f["start"] < t for s, t in gold_spans)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--per-set", type=int, default=40)
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args(argv)
    env = load_env()
    os.environ["FIREWORKS_API_KEY"] = env["FIREWORKS_API_KEY"]
    started, git = time.time(), git_version()
    client = Fireworks(account_id=ACCOUNT)
    model = a.model if "/" in a.model else f"accounts/{ACCOUNT}/models/{a.model}"
    dep_id = f"ms-er-pipe-{time.strftime('%m%d-%H%M')}"
    route = f"{model}#accounts/{ACCOUNT}/deployments/{dep_id}"
    out = RESULTS / "entity-resolution-pipeline" / new_run_id(a.tag, started, git)
    out.mkdir(parents=True, exist_ok=True)
    try:
        log(f"creating live-merge deployment {dep_id}")
        client.deployments.create(base_model=model, deployment_id=dep_id, deployment_shape=shape_for(client, model),
                                  min_replica_count=0, max_replica_count=1, display_name="muse-shield pipeline test")
        wait_serving(client, dep_id, route, env["FIREWORKS_API_KEY"])
        backend = GlimmerBackend("https://api.fireworks.ai/inference/v1", route, env["FIREWORKS_API_KEY"], max_tokens=4000, timeout=300.0)
        sets = {"examples": json.loads((REPO / "data/er-playground/examples.json").read_text())}
        rng = random.Random(3)
        for name in ("test", "challenge", "ambiguity"):
            docs = [json.loads(l) for l in (REPO / "runs/er/v1" / f"{name}.docs.jsonl").read_text().splitlines() if l.strip()]
            sets[name] = rng.sample(docs, min(a.per_set, len(docs)))
        report = {"model": model, "route": route, "git": git, "sets": {}}
        for name, docs in sets.items():
            t0 = time.time()
            with ThreadPoolExecutor(a.workers) as pool:
                rows = list(pool.map(lambda d: run_doc(backend, d), docs))
            (out / f"{name}.rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
            ok = [r for r in rows if "pred" in r]
            agg = {"docs": len(docs), "valid": len(ok), "seconds": round(time.time() - t0, 1),
                   "calls_per_doc": round(sum(r["calls"] for r in rows) / max(len(rows), 1), 1),
                   "classify_valid": sum(r["prompt_categories"] is not None for r in ok),
                   "seconds_per_doc": round(sum(r["seconds"] for r in ok) / max(len(ok), 1), 1)}
            want = (lambda r, d: FAMILY_CATS.get(d.get("family"), set())) if name != "examples" else \
                   (lambda r, d: SECTOR_CATS.get(d.get("sector"), set()))
            by_id = {(d.get("uid") or d.get("id")): d for d in docs}
            for key in ("prompt_categories", "rule_categories"):
                hit = sum(bool(set(r[key] or []) & want(r, by_id[r["uid"]])) for r in ok)
                agg[f"{key}_hit"] = round(hit / max(len(ok), 1), 3)
            if name != "examples":
                ls = [leak_stats(by_id[r["uid"]], r) for r in ok]
                tot = {k: sum(x[k] for x in ls) for k in ls[0]}
                agg.update({"leak_before": round(tot["leak_before"] / tot["total"], 4),
                            "leak_after": round(tot["leak_after"] / tot["total"], 4),
                            "fallback_spans": tot["fallback"], "fallback_false_alarms": tot["fallback_false"]})
            report["sets"][name] = agg
            log(f"{name}: {json.dumps(agg)}")
        (out / "report.json").write_text(json.dumps(report, indent=1))
        log(f"recorded {out}")
    finally:
        try:
            client.deployments.delete(dep_id, ignore_checks=True)
            log(f"deleted {dep_id}")
        except Exception as exc:  # noqa: BLE001
            log(f"DELETE FAILED for {dep_id}: {exc} (still billing: delete it by hand)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
