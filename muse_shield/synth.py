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
import threading
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

FIRST = ["Aarav", "Ishita", "Kabir", "Meenakshi", "Rehan", "Tanya", "Sameer", "Lavanya", "Joseph", "Fatima", "Harpreet", "Deepa",
         "Arnav", "Nandini", "Yusuf", "Bhavna", "Clara", "Mihir", "Shreya", "Gaurav", "Anika", "Wen", "Diego", "Amara", "Sven", "Leila",
         "Pranav", "Rukmini", "Tobias", "Keerthi", "Imran", "Jasleen", "Oliver", "Sana", "Vivek", "Priyanka", "Kenji", "Esther"]
LAST = ["Bhattacharya", "Narayanan", "Gill", "Sood", "Pillai", "Chakraborty", "Rao", "Kulkarni", "D'Souza", "Ansari", "Mehra",
        "Venkatesh", "Thakur", "Banerjee", "Fernandes", "Iyengar", "Lobo", "Chopra", "Ramaswamy", "Okonkwo", "Lindholm", "Haddad",
        "Moreno", "Tanaka", "Weber", "Mukherjee", "Saxena", "Dutta", "Kapoor", "Menon"]
ORG_A = ["Vardhan", "Silverline", "Bluegate", "Konark", "Northstar", "Tarang", "Evergreen", "Sahyadri", "Crescent", "Pinnacle",
         "Arcadia", "Indus", "Lumina", "Maple", "Orion", "Saffron", "Trident", "Zenith", "Coral", "Granite"]
ORG_B = ["Capital", "Pharma", "Logistics", "Retail", "Healthcare", "Holdings", "Technologies", "Foods", "Ventures", "Hospital",
         "Insurance", "Finserv", "Textiles", "Labs", "Motors"]
STREETS = ["MG Road", "Linking Road", "Residency Road", "Anna Salai", "Park Street", "FC Road", "Banjara Hills Road No. 3",
           "Sector 18", "Hill Road", "Brigade Road", "Civil Lines", "Ring Road"]
CITIES = [("Mumbai", "400"), ("Bengaluru", "560"), ("Chennai", "600"), ("Kolkata", "700"), ("Pune", "411"), ("Hyderabad", "500"),
          ("Delhi", "110"), ("Ahmedabad", "380"), ("Jaipur", "302"), ("Kochi", "682"), ("Lucknow", "226"), ("Indore", "452")]


def identity_pack(rng: random.Random) -> dict:
    """Fictional, randomly generated details for one document, so no two documents share values."""
    people = []
    for _ in range(3):
        f, l = rng.choice(FIRST), rng.choice(LAST)
        people.append(f"{f} {l}")
    city, pin = rng.choice(CITIES)
    org = f"{rng.choice(ORG_A)} {rng.choice(ORG_B)}"
    first = people[0].split()[0].lower()
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return {
        "people": people,
        "organization": org,
        "phone": f"+91 {rng.choice('6789')}{rng.randint(1000, 9999)} {rng.randint(10000, 99999)}",
        "email": f"{first}.{people[0].split()[1].lower().replace(chr(39), '')}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'outlook.com', org.split()[0].lower() + '.in'])}",
        "aadhaar_like": f"{rng.randint(2, 9)}{rng.randint(100, 999)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}",
        "pan_like": "".join(rng.choice(letters) for _ in range(3)) + "P" + rng.choice(letters) + f"{rng.randint(1000, 9999)}" + rng.choice(letters),
        "ifsc_like": "".join(rng.choice(letters) for _ in range(4)) + "0" + "".join(rng.choice("0123456789") for _ in range(6)),
        "account_number": "".join(rng.choice("0123456789") for _ in range(rng.choice([11, 12, 14]))),
        "address": f"{rng.randint(1, 450)}, {rng.choice(['Sunrise Apartments', 'Lake View Towers', 'Green Park Society', 'Shanti Nagar', 'Palm Grove Layout'])}, {rng.choice(STREETS)}, {city} {pin}{rng.randint(1, 99):03d}",
        "date": f"{rng.randint(1, 28)} {rng.choice(['January', 'March', 'May', 'July', 'September', 'November'])} {rng.choice([2025, 2026, 2027])}",
        "amount": rng.choice([f"₹{rng.randint(2, 95)} lakh", f"₹{rng.randint(1, 900)} crore", f"${rng.randint(2, 950)},{rng.randint(100, 999)}", f"₹{rng.randint(1, 99)},{rng.randint(100, 999)}"]),
    }


PACK_VALUE_KEYS = ["phone", "email", "aadhaar_like", "pan_like", "ifsc_like", "account_number"]

GEN_PROMPT_PACKED = """Write ONE realistic workplace document of this type: "{doc_type}" (sector: {sector}).
Use these fictional details, copied exactly, wherever they fit naturally (at least 6 of them):
{pack}
Rules: everything is fictional; do not invent other phone numbers, emails or ID numbers than the ones given; you may add
nicknames, initials, job titles, relative dates and harmless generic phrases. Include confidential business or HR context where
it fits the document type. 2 to 5 paragraphs separated by blank lines. No placeholders like [NAME].
Reply with JSON only: {{"doc_type": "...", "text": "..."}}"""

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


# One cap on concurrent Meta API calls for the whole process. Contributor mode allows 150 requests a
# minute per team; at ~5-6 s per reasoning call, ~12 in flight uses that fully. More only buys 429s.
API_SLOTS = threading.BoundedSemaphore(int(os.environ.get("SYNTH_API_CONCURRENCY", "12")))


class _CappedSpark(MetaModelBackend):
    def _call(self, messages):
        with API_SLOTS:
            return super()._call(messages)


def spark(model: str, effort: str, max_tokens: int = 8192) -> MetaModelBackend:
    load_env()
    return _CappedSpark(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), model, os.environ["MODEL_API_KEY"],
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


def generate_one(sector: str, doc_type: str, pack: dict, model: str) -> tuple[dict | None, dict]:
    b = spark(model, "medium", max_tokens=8192)
    pack_text = "\n".join(f"- {k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in pack.items())
    msg = [{"role": "user", "content": GEN_PROMPT_PACKED.format(doc_type=doc_type, sector=SECTORS[sector]["name"], pack=pack_text)}]
    raw, usage = b._call(msg)
    try:
        d = json.loads(raw)
    except ValueError:
        return None, usage
    text = d.get("text") or ""
    return ({"sector": sector, "doc_type": doc_type, "text": text, "pack": pack} if text else None), usage


def pack_misses(paragraph: str, entities: list[dict], pack: dict) -> list[str]:
    """Planted identifiers present in this paragraph but not covered by any label: independent ground truth."""
    misses = []
    values = [pack[k] for k in PACK_VALUE_KEYS] + list(pack.get("people", []))
    for v in values:
        if v and v in paragraph and not any(v in e["text"] or e["text"] in v and len(e["text"]) >= 4 for e in entities):
            misses.append(v)
    return misses


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
    """Label every paragraph with both passes concurrently (the global API cap keeps the total in check)."""
    paras = [p for _, p in paragraphs(doc["text"])]
    with ThreadPoolExecutor(max_workers=max(1, 2 * len(paras))) as pool:
        futs = [(p, pool.submit(low.analyze_one, p), pool.submit(med.analyze_one, p)) for p in paras]
        labelled = [(p, fa.result(), fb.result()) for p, fa, fb in futs]
    out = []
    for para, a, b in labelled:
        sentences = split_sentences(para) or [para]
        if not (a.valid and b.valid):
            continue
        g = agree(a, b)
        if g is None:
            out.append({"dropped": True, "reason": "disagreement", "paragraph": para, "low": [(s.text, s.type) for s in a.entities],
                        "medium": [(s.text, s.type) for s in b.entities]})
            continue
        if doc.get("pack"):
            missed = pack_misses(para, g["entities"], doc["pack"])
            if missed:
                out.append({"dropped": True, "reason": "planted PII unlabelled", "paragraph": para, "missed": missed})
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




# -- at-scale generation with planted identities, train/test split, resumable ----------------------

def build_scale(out: Path, sectors: list[str], train_docs: int, test_docs: int, seed: int, model: str, workers: int) -> dict:
    """Generate, double-label and verify documents per sector; split by document into train/test.

    Resumable: finished documents are appended to <split>/rows.jsonl (+ manifest) as they complete,
    and docs already recorded in done.jsonl are skipped on restart.
    """
    os.environ.setdefault("META_SYNTHETIC_ONLY", "1")
    out.mkdir(parents=True, exist_ok=True)
    done_file = out / "done.jsonl"
    done = {json.loads(l)["doc_id"] for l in done_file.read_text().splitlines()} if done_file.exists() else set()
    jobs = []
    for sector in sectors:
        rng = random.Random(f"{seed}:{sector}")
        for i in range(train_docs + test_docs):
            doc_id = f"{sector}-{i:04d}"
            split = "test" if i < test_docs else "train"
            jobs.append((doc_id, split, sector, rng.choice(SECTORS[sector]["doc_types"]), identity_pack(rng)))
    jobs = [j for j in jobs if j[0] not in done]
    low, med = spark(model, "low", 4096), spark(model, "medium", 8192)
    import threading

    lock = threading.Lock()
    t0 = time.time()

    def work(job):
        doc_id, split, sector, doc_type, pack = job
        try:
            doc, gen_usage = generate_one(sector, doc_type, pack, model)
        except Exception as exc:  # noqa: BLE001
            return {"doc_id": doc_id, "error": str(exc)[:200]}
        if not doc:
            return {"doc_id": doc_id, "error": "generation returned no document"}
        rows = label_doc(doc, low, med)
        kept = [r for r in rows if not r.get("dropped")]
        dropped = [r for r in rows if r.get("dropped")]
        with lock:
            d = out / split
            d.mkdir(exist_ok=True)
            with (d / "rows.jsonl").open("a") as f, (d / "rows.manifest.jsonl").open("a") as m:
                for r in kept:
                    f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
                    m.write(json.dumps({**r["_meta"], "doc_id": doc_id, "split": split}, ensure_ascii=False) + "\n")
            with (d / "dropped.jsonl").open("a") as f:
                for r in dropped:
                    f.write(json.dumps({**r, "doc_id": doc_id}, ensure_ascii=False) + "\n")
            with (d / "docs.jsonl").open("a") as f:
                f.write(json.dumps({**doc, "doc_id": doc_id}, ensure_ascii=False) + "\n")
            with done_file.open("a") as f:
                f.write(json.dumps({"doc_id": doc_id, "kept": len(kept), "dropped": len(dropped),
                                    "gen_usage": gen_usage, "t": time.time()}) + "\n")
        return {"doc_id": doc_id, "kept": len(kept), "dropped": len(dropped)}

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, r in enumerate(pool.map(work, jobs), 1):
            results.append(r)
            if i % 25 == 0:
                print(f"{i}/{len(jobs)} docs · {time.time() - t0:.0f}s", flush=True)
    summary = {"sectors": sectors, "train_docs_per_sector": train_docs, "test_docs_per_sector": test_docs,
               "docs_done_now": len(results), "errors": sum("error" in r for r in results),
               "rows_kept_now": sum(r.get("kept", 0) for r in results), "rows_dropped_now": sum(r.get("dropped", 0) for r in results),
               "seconds": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def scale_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.synth scale")
    ap.add_argument("--sectors", default="ma_legal,healthcare,ecommerce,admin")
    ap.add_argument("--train-docs", type=int, default=400)
    ap.add_argument("--test-docs", type=int, default=75)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--model", default="muse-spark-1.3-contributor")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=Path("runs/synth/v2"))
    a = ap.parse_args(argv)
    print(json.dumps(build_scale(a.out, a.sectors.split(","), a.train_docs, a.test_docs, a.seed, a.model, a.workers), indent=2))
    return 0


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(scale_main(_sys.argv[2:]) if len(_sys.argv) > 1 and _sys.argv[1] == "scale" else main())
