"""Realistic synthetic training documents per sector, written and double-labelled by Muse Spark.

    python -m muse_shield.synth --sectors ma_legal,healthcare,ecommerce --docs 4 --out runs/synth/trial

1. generate: Muse Spark (Contributor, medium reasoning) writes realistic documents for a sector:
   emails, notes, memos, tickets, with fictional people and organizations.
2. label twice: each paragraph goes through the production analysis prompt at low and at medium
   reasoning effort, independently.
3. agree: keep an entity only if both passes found the same (text, type); keep a context only if
   both found an overlapping one of the same kind. Paragraphs where the passes disagree on more
   than `max_disagreement` of entities are dropped instead of patched.

Contributor mode lets Meta train on prompts and responses: fine for fictional data only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .analysis import split_sentences
from .backends import MetaModelBackend
from .benchmarks.nemotron import paragraphs
from .config import load_env
from .trainset import chat_row

SECTORS = {
    "ma_legal": {
        "name": "M&A, finance and legal",
        "doc_types": ["board email about an acquisition", "term sheet summary", "NDA cover email", "due-diligence findings memo",
                      "legal counsel advice email", "investor update with financials", "settlement negotiation email",
                      "loan restructuring note"],
    },
    "healthcare": {
        "name": "Healthcare",
        "doc_types": ["clinical visit note", "patient appointment email", "insurance claim submission", "specialist referral letter",
                      "lab results message to a patient", "hospital discharge summary", "pharmacy prescription query",
                      "HR email about a staff member's medical leave"],
    },
    "ecommerce": {
        "name": "E-commerce and customer support",
        "doc_types": ["order confirmation email", "refund request from a customer", "delivery complaint ticket",
                      "support agent reply with account details", "return pickup scheduling email", "chargeback dispute note",
                      "loyalty account update", "seller payout query"],
    },
    "admin": {
        "name": "Daily office and admin",
        "doc_types": ["meeting scheduling email", "travel booking request", "expense reimbursement email", "onboarding email for a new hire",
                      "vendor invoice follow-up", "salary revision letter", "leave approval email", "IT access request"],
    },
}

GEN_PROMPT = """Write {n} realistic, varied workplace documents for the sector "{sector}".
Document types to draw from: {types}.
Requirements:
- Every person, company, address, ID, account and number is FICTIONAL but realistic. Mix Indian and international details
  (names, +91 and other phone formats, PAN/Aadhaar-like IDs, IFSC codes, emails, street addresses, amounts in ₹/lakh/crore and $).
- Include the sensitive things a privacy filter must catch: names, contact details, IDs, account/card numbers, addresses,
  specific dates and times, amounts with a clear role (salary, price, deal value, loan, fee), health details where relevant,
  and confidential business context (deals, decisions, plans, negotiations, HR matters).
- Make them hard in realistic ways: nicknames and initials, a person mentioned twice differently, numbers inside sentences,
  a paragraph with nothing sensitive, and generic phrases that should NOT be masked.
- 2 to 5 paragraphs each, separated by blank lines. No placeholders like [NAME].
Reply with JSON only: {{"documents": [{{"doc_type": "...", "text": "..."}}]}}"""


def spark(model: str, effort: str, max_tokens: int = 8192) -> MetaModelBackend:
    load_env()
    return MetaModelBackend(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), model, os.environ["MODEL_API_KEY"],
                            name=f"spark-{effort}", synthetic_only=True, reasoning_effort=effort, max_tokens=max_tokens)


def generate(sector: str, n: int, seed: int, model: str) -> tuple[list[dict], dict]:
    spec = SECTORS[sector]
    rng = random.Random(seed)
    types = rng.sample(spec["doc_types"], min(len(spec["doc_types"]), max(3, n)))
    b = spark(model, "medium", max_tokens=16384)
    msg = [{"role": "user", "content": GEN_PROMPT.format(n=n, sector=spec["name"], types="; ".join(types))}]
    raw, usage = b._call(msg)
    try:
        docs = json.loads(raw)["documents"]
    except (ValueError, KeyError, TypeError):
        docs = []
    return [{"sector": sector, "doc_type": d.get("doc_type", ""), "text": d.get("text", "")} for d in docs if d.get("text")], usage


def agree(a, b, max_disagreement: float = 0.34) -> dict | None:
    ea, eb = {(s.text, s.type): s.role for s in a.entities}, {(s.text, s.type): s.role for s in b.entities}
    both = ea.keys() & eb.keys()
    union = ea.keys() | eb.keys()
    if union and 1 - len(both) / len(union) > max_disagreement:
        return None
    entities = []
    for text, etype in sorted(both, key=lambda k: a.paragraph.find(k[0])):
        e = {"text": text, "type": etype}
        if etype == "AMOUNT":
            e["role"] = ea[(text, etype)] if ea[(text, etype)] == eb[(text, etype)] else "OTHER"
        entities.append(e)
    contexts = [{"sentences": c.sentences, "kind": c.kind, "subtype": c.subtype, "refers_to": None, "summary": c.summary}
                for c in a.contexts if any(d.kind == c.kind and set(d.sentences) & set(c.sentences) for d in b.contexts)]
    return {"entities": entities, "contexts": contexts, "agreement": len(both) / len(union) if union else 1.0}


def label_doc(doc: dict, low: MetaModelBackend, med: MetaModelBackend) -> list[dict]:
    out = []
    for _, para in paragraphs(doc["text"]):
        sentences = split_sentences(para) or [para]
        a, b = low.analyze_one(para), med.analyze_one(para)
        if not (a.valid and b.valid):
            continue
        g = agree(a, b)
        if g is None:
            out.append({"dropped": True, "paragraph": para, "low": [(s.text, s.type) for s in a.entities],
                        "medium": [(s.text, s.type) for s in b.entities]})
            continue
        row = chat_row(sentences, json.dumps({"entities": g["entities"], "contexts": g["contexts"]}, ensure_ascii=False))
        row["_meta"] = {"source": "synthetic-spark", "domain": doc["sector"], "doc_type": doc["doc_type"], "agreement": g["agreement"],
                        "usage_low": a.usage, "usage_medium": b.usage}
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.synth")
    ap.add_argument("--sectors", default="ma_legal,healthcare,ecommerce")
    ap.add_argument("--docs", type=int, default=4, help="documents per sector")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--model", default="muse-spark-1.3-contributor")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=Path("runs/synth/trial"))
    args = ap.parse_args(argv)
    os.environ.setdefault("META_SYNTHETIC_ONLY", "1")
    t0 = time.time()
    sectors = [s.strip() for s in args.sectors.split(",")]
    with ThreadPoolExecutor(max_workers=len(sectors)) as pool:
        gen = list(pool.map(lambda s: generate(s, args.docs, args.seed, args.model), sectors))
    docs = [d for ds, _ in gen for d in ds]
    t_gen = time.time()
    low, med = spark(args.model, "low", 4096), spark(args.model, "medium", 8192)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        labelled = list(pool.map(lambda d: label_doc(d, low, med), docs))
    t_lab = time.time()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [r for rs in labelled for r in rs if not r.get("dropped")]
    dropped = [r for rs in labelled for r in rs if r.get("dropped")]
    (args.out / "docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs))
    (args.out / "rows.jsonl").write_text("".join(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n" for r in rows))
    (args.out / "rows.manifest.jsonl").write_text("".join(json.dumps(r["_meta"], ensure_ascii=False) + "\n" for r in rows))
    (args.out / "dropped.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in dropped))
    usage = {"gen_in": sum(u.get("prompt_tokens", 0) for _, u in gen), "gen_out": sum(u.get("completion_tokens", 0) for _, u in gen),
             "label_in": sum(r["_meta"]["usage_low"].get("prompt_tokens", 0) + r["_meta"]["usage_medium"].get("prompt_tokens", 0) for r in rows),
             "label_out": sum(r["_meta"]["usage_low"].get("completion_tokens", 0) + r["_meta"]["usage_medium"].get("completion_tokens", 0) for r in rows)}
    cost = ((usage["gen_in"] + usage["label_in"]) * 0.10 + (usage["gen_out"] + usage["label_out"]) * 0.20) / 1e6  # contributor rates, uncached
    summary = {"docs": len(docs), "docs_by_sector": {s: sum(d["sector"] == s for d in docs) for s in sectors},
               "paragraph_rows_kept": len(rows), "paragraphs_dropped_for_disagreement": len(dropped),
               "mean_agreement_kept": round(sum(r["_meta"]["agreement"] for r in rows) / max(len(rows), 1), 3),
               "seconds": {"generate": round(t_gen - t0, 1), "label": round(t_lab - t_gen, 1), "total": round(t_lab - t0, 1)},
               "usage": usage, "cost_usd_upper_bound": round(cost, 4)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
