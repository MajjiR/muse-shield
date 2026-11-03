"""Ten realistic multi-line messages, run through call 1 in a loop, to see exactly what gets missed.

    MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.realistic --rounds 3

Every value is invented (fake people, numbers and companies), shaped like real traffic:
HR mail, a medical note, a support chat, a board memo, a booking, an incident report with
secrets, a tax question, a school letter, a WhatsApp negotiation and a GST invoice.

Per example:
    must      values that must not reach the chat model (a leak if any of it is visible)
    optional  borderline values (public places, flight numbers): reported, not scored
    keep      phrases that must stay readable (the user's actual question)
    contexts  context-block kinds we expect (reported, not scored as leaks)

A value counts as protected when at least half its characters are covered by a masked span
or a context block and the exact value doesn't appear in the masked text.
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .app.engine import Masker
from .app.server import analyzer_from_env
from .app.vault import Vault


@dataclass
class Example:
    id: str
    title: str
    text: str
    must: list[tuple[str, str]]  # (value, expected type)
    optional: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)


EXAMPLES = [
    Example("hr-transfer", "HR email: transfer, salary, bank details", """Hi Kavya,

Following our call, I'm confirming that Arjun Malhotra (Employee ID EMP-20417) will move to the Pune office from 1 December. His revised CTC is ₹28 lakh per annum.

Please update his bank details: HDFC Bank, account 50100234567891, IFSC HDFC0001234. His PAN is ABCPM1234K.

Keep this confidential until the reorg is announced.

Thanks,
Neha Kapoor
HR Business Partner, Zentrix Software""",
        must=[("Kavya", "PERSON"), ("Arjun Malhotra", "PERSON"), ("EMP-20417", "ID"), ("₹28 lakh per annum", "AMOUNT"),
              ("50100234567891", "ID"), ("HDFC0001234", "ID"), ("ABCPM1234K", "ID"), ("Neha Kapoor", "PERSON"),
              ("Zentrix Software", "ORG")],
        optional=["Pune", "1 December", "HDFC Bank"], contexts=["HR"]),

    Example("medical-intake", "Clinic intake note: DOB, MRN, diagnosis, insurance", """Patient: Meera Krishnan, DOB 14/03/1987, MRN 7781-2290.
Address: 44 Lake Road, Kochi 682011. Phone: +91 98470 12345.

Presenting with type 2 diabetes and mild hypertension. Currently on metformin 500 mg twice daily.

Insurance: Star Health policy SH-99012345. Emergency contact: her husband Ravi Krishnan, ravi.k@gmail.com.""",
        must=[("Meera Krishnan", "PERSON"), ("14/03/1987", "DATE"), ("7781-2290", "ID"), ("44 Lake Road, Kochi 682011", "ADDRESS"),
              ("+91 98470 12345", "CONTACT"), ("type 2 diabetes", "SENSITIVE_ATTRIBUTE"), ("mild hypertension", "SENSITIVE_ATTRIBUTE"),
              ("SH-99012345", "ID"), ("Ravi Krishnan", "PERSON"), ("ravi.k@gmail.com", "CONTACT")],
        optional=["metformin 500 mg", "Star Health"]),

    Example("card-support-chat", "Support chat: card number, CVV, UPI, password", """[10:42] Customer: hi my card got blocked, number is 4539 1488 0343 6467, expiry 09/27, cvv 312
[10:43] Agent (Sana): Hi! Can you confirm your registered mobile and the last transaction?
[10:44] Customer: 9876543210, i paid ₹1,299 to Swiggy yesterday. my UPI is vikram.rao@okicici
[10:45] Customer: also my netbanking password is Vikram@2024 if that helps""",
        must=[("4539 1488 0343 6467", "ID"), ("312", "SECRET"), ("Sana", "PERSON"), ("9876543210", "CONTACT"),
              ("vikram.rao@okicici", "CONTACT"), ("Vikram@2024", "SECRET")],
        optional=["09/27", "₹1,299", "Swiggy"]),

    Example("board-term-sheet", "Board memo: term sheet, valuation, founders", """PRIVILEGED & CONFIDENTIAL

To: Board of Directors, Halcyon Robotics Pvt Ltd
From: Aditya Bose, General Counsel

We have received a non-binding term sheet from Corvex Capital valuing the company at $85 million pre-money, with a $15 million Series B led by Corvex. Closing is targeted for 15 January 2027.

The founders, Ishita Rao and Karan Mehta, will retain board seats. Please do not discuss this outside the board.""",
        must=[("Halcyon Robotics Pvt Ltd", "ORG"), ("Aditya Bose", "PERSON"), ("Corvex Capital", "ORG"), ("$85 million", "AMOUNT"),
              ("$15 million", "AMOUNT"), ("Ishita Rao", "PERSON"), ("Karan Mehta", "PERSON")],
        optional=["15 January 2027"], contexts=["DEAL"]),

    Example("travel-booking", "Booking confirmation: passport, contact, card tail", """Booking ref: QX7HT2
Passenger: Mr. Daniel Okafor
Passport: A12345678 (Nigeria), expires 2031-05-19
Flight: LH 761 Frankfurt to Bengaluru, 12 Dec 2026, seat 14C

Hotel: The Leela Palace Bengaluru, 23 Old Airport Road. Paid with Visa ending 4421.
Contact: daniel.okafor@outlook.com, +49 151 23456789""",
        must=[("QX7HT2", "ID"), ("Daniel Okafor", "PERSON"), ("A12345678", "ID"), ("daniel.okafor@outlook.com", "CONTACT"),
              ("+49 151 23456789", "CONTACT")],
        optional=["2031-05-19", "LH 761", "12 Dec 2026", "23 Old Airport Road", "4421", "The Leela Palace Bengaluru"]),

    Example("incident-secrets", "Incident report: AWS key, Stripe key, DB password, IP", """Incident INC-4471: production outage on 2 Nov

Root cause: a leaked AWS key AKIAIOSFODNN7EXAMPLE was used from IP 203.0.113.45 to delete the S3 bucket acme-prod-backups.

The on-call engineer, Tomás García (tomas@acme.dev), rotated the key. Our Stripe secret sk_live_51Hx9QeKZ2mNpLq7Rt8Vw3Yb was also in the same .env file and has been revoked.

Database host: db-prod-3.internal.acme.dev, user admin, password Pr0d!Acme#2026.""",
        must=[("AKIAIOSFODNN7EXAMPLE", "SECRET"), ("203.0.113.45", "ID"), ("Tomás García", "PERSON"), ("tomas@acme.dev", "CONTACT"),
              ("sk_live_51Hx9QeKZ2mNpLq7Rt8Vw3Yb", "SECRET"), ("db-prod-3.internal.acme.dev", "CONTACT"), ("Pr0d!Acme#2026", "SECRET")],
        optional=["INC-4471", "acme-prod-backups", "2 Nov"]),

    Example("tax-question", "Tax question: Aadhaar, PAN, income, rent, loan", """Hi, I'm Sunita Verma. My Aadhaar is 2345 6789 0123 and PAN BNZPV4567L.

Last year I earned ₹14.5 lakh from Infosys and ₹2.1 lakh rent from my flat at B-302, Sai Residency, Hyderabad 500032. I also have a home loan of ₹38 lakh with SBI.

Can you tell me how much tax I'll owe under the new regime?""",
        must=[("Sunita Verma", "PERSON"), ("2345 6789 0123", "ID"), ("BNZPV4567L", "ID"), ("₹14.5 lakh", "AMOUNT"),
              ("₹2.1 lakh", "AMOUNT"), ("B-302, Sai Residency, Hyderabad 500032", "ADDRESS"), ("₹38 lakh", "AMOUNT")],
        optional=["Infosys", "SBI"], keep=["how much tax I'll owe under the new regime"]),

    Example("school-letter", "School letter: a child's name and diagnosis", """Dear Mrs. Fernandes,

Your son Aarav Fernandes (Class 4B, roll no. 17) was seen by the school counsellor today after an incident with another student. He mentioned he has been diagnosed with ADHD.

Please call me at 022-2654 8890 or reply to principal@stxaviers-bandra.edu.in.

Regards,
Fr. Joseph D'Souza, Principal""",
        must=[("Mrs. Fernandes", "PERSON"), ("Aarav Fernandes", "PERSON"), ("ADHD", "SENSITIVE_ATTRIBUTE"), ("022-2654 8890", "CONTACT"),
              ("principal@stxaviers-bandra.edu.in", "CONTACT"), ("Joseph D'Souza", "PERSON")],
        optional=["Class 4B", "roll no. 17"]),

    Example("flat-negotiation", "WhatsApp: flat price negotiation, PAN, phone", """Rahul: Bhai, the owner of Flat 1102, Prestige Lakeside, Whitefield is asking ₹1.85 crore
Rahul: we offered ₹1.6 crore, he said he'll go down to ₹1.75 if we close by Diwali
Me: ok tell him 1.7 final, token amount ₹5 lakh by NEFT. My number for the agreement is 99001 23456
Rahul: done, his name is Mr. Prakash Shetty, PAN on the sale deed will be AQWPS7788J""",
        must=[("Rahul", "PERSON"), ("Flat 1102, Prestige Lakeside, Whitefield", "ADDRESS"), ("₹1.85 crore", "AMOUNT"), ("₹1.6 crore", "AMOUNT"),
              ("₹5 lakh", "AMOUNT"), ("99001 23456", "CONTACT"), ("Prakash Shetty", "PERSON"), ("AQWPS7788J", "ID")],
        optional=["₹1.75", "1.7 final", "Diwali"], contexts=["NEGOTIATION"]),

    Example("gst-invoice", "GST invoice: GSTINs, bank account, contacts", """Tax Invoice #INV-2026-0912
Vendor: Brightline Logistics LLP, GSTIN 27AAKFB1234C1Z5, 4th Floor, Kamala Mills, Lower Parel, Mumbai 400013
Bill to: Oakmont Retail Pvt Ltd, GSTIN 29AABCO5678D1Z2

Freight charges for October: ₹3,42,000 + 18% GST = ₹4,03,560.
Pay to: ICICI Bank A/c 000405112233, IFSC ICIC0000004.
Contact: accounts@brightline.in / Suresh Nair, 98200 55667""",
        must=[("Brightline Logistics LLP", "ORG"), ("27AAKFB1234C1Z5", "ID"), ("4th Floor, Kamala Mills, Lower Parel, Mumbai 400013", "ADDRESS"),
              ("Oakmont Retail Pvt Ltd", "ORG"), ("29AABCO5678D1Z2", "ID"), ("₹3,42,000", "AMOUNT"), ("₹4,03,560", "AMOUNT"),
              ("000405112233", "ID"), ("ICIC0000004", "ID"), ("accounts@brightline.in", "CONTACT"), ("Suresh Nair", "PERSON"),
              ("98200 55667", "CONTACT")],
        optional=["INV-2026-0912", "ICICI Bank"]),
]


def covered(text: str, value: str, spans: list[dict]) -> tuple[float, str | None]:
    """Fraction of the value's characters under a masked span or context block, plus the covering entity's type."""
    start = text.find(value)
    if start < 0:
        raise ValueError(f"gold value not in text: {value!r}")
    end = start + len(value)
    chars = set(range(start, end))
    hit_type = None
    masked = set()
    for s in spans:
        overlap = chars & set(range(s["start"], s["end"]))
        if overlap:
            masked |= overlap
            if s["kind"] == "entity" and hit_type is None:
                hit_type = s["type"]
    return len(masked) / len(chars), hit_type


def score(ex: Example, result) -> dict:
    masked_text = result.masked_text
    misses, partial, wrong_type = [], [], []
    for value, etype in ex.must:
        frac, got = covered(ex.text, value, result.spans)
        visible = value.casefold() in masked_text.casefold()
        if visible or frac < 0.5:
            misses.append({"value": value, "type": etype, "covered": round(frac, 2)})
        else:
            if frac < 1:
                partial.append({"value": value, "type": etype, "covered": round(frac, 2)})
            if got and got != etype and not (etype == "AMOUNT" and got == "AMOUNT"):
                wrong_type.append({"value": value, "expected": etype, "got": got})
    optional = {v: covered(ex.text, v, result.spans)[0] >= 0.5 for v in ex.optional}
    kept = {k: k in masked_text for k in ex.keep}
    gold_ranges = []
    for v, _ in ex.must:
        i = ex.text.find(v)
        gold_ranges.append((i, i + len(v)))
    for v in ex.optional:
        i = ex.text.find(v)
        gold_ranges.append((i, i + len(v)))
    gold_values = {v.casefold() for v, _ in ex.must} | {v.casefold() for v in ex.optional}
    # Over-masking: masked entities that are neither a gold value nor overlap one (repeats of a gold value don't count).
    extra = sorted({s["text"] for s in result.spans if s["kind"] == "entity" and s["text"].casefold() not in gold_values
                    and not any(s["start"] < e and b < s["end"] for b, e in gold_ranges)})
    kinds = sorted({c["kind"] for c in result.contexts})
    return {"id": ex.id, "ok": result.analysis_ok, "error": result.error, "must": len(ex.must), "missed": misses,
            "partial": partial, "wrong_type": wrong_type, "optional_masked": optional, "kept": kept,
            "extra_masked": extra, "contexts": kinds, "contexts_expected": ex.contexts,
            "masked_text": masked_text, "latency_ms": round(result.latency_ms), "cost_usd": result.cost_usd or 0.0}


def run(rounds: int = 3, examples: list[Example] = EXAMPLES, analyzer=None) -> dict:
    analyzer = analyzer or analyzer_from_env()[0]
    if analyzer is None:
        raise SystemExit("analysis is off: " + analyzer_from_env()[1])
    t0 = time.perf_counter()
    rows = []
    for r in range(1, rounds + 1):
        vault = Vault(":memory:", os.urandom(32))  # fresh vault per round: no carry-over between rounds
        masker = Masker(vault, analyzer)
        for ex in examples:
            chat = vault.create_chat()
            res = masker.mask(ex.text, chat)
            row = score(ex, res)
            row["round"] = r
            rows.append(row)
            leaks = ", ".join(m["value"] for m in row["missed"]) or "none"
            print(f"round {r} · {ex.id:20} missed {len(row['missed'])}/{row['must']}: {leaks}", flush=True)

    must_total = sum(r["must"] for r in rows)
    missed_total = sum(len(r["missed"]) for r in rows)
    by_type_total, by_type_missed = Counter(), Counter()
    for ex in examples:
        for _, t in ex.must:
            by_type_total[t] += rounds
    miss_count: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        for m in r["missed"]:
            by_type_missed[m["type"]] += 1
            miss_count[(r["id"], m["value"])] += 1
    return {
        "rounds": rounds, "examples": len(examples), "seconds": round(time.perf_counter() - t0, 1),
        "model": getattr(analyzer, "model", "?"), "reasoning_effort": getattr(analyzer, "extra", {}).get("reasoning_effort"),
        "must_total": must_total, "missed_total": missed_total,
        "leak_rate": missed_total / must_total if must_total else None,
        "span_recall": 1 - missed_total / must_total if must_total else None,
        "valid_rate": sum(r["ok"] for r in rows) / len(rows),
        "recall_by_type": {t: 1 - by_type_missed[t] / n for t, n in sorted(by_type_total.items())},
        "missed_by_type": dict(by_type_missed),
        "consistent_misses": sorted([{"id": k[0], "value": k[1], "times": v} for k, v in miss_count.items()], key=lambda x: -x["times"]),
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 5),
        "rows": rows,
    }


def render(rep: dict) -> str:
    pct = lambda x: "–" if x is None else f"{x:.1%}"  # noqa: E731
    lines = [f"# Realistic PII loop · {rep['examples']} examples × {rep['rounds']} rounds",
             "", f"model `{rep['model']}` (reasoning {rep['reasoning_effort']}) · {rep['seconds']}s · ${rep['cost_usd']:.4f}", "",
             f"**Missed {rep['missed_total']} of {rep['must_total']} must-mask values ({pct(rep['leak_rate'])} leak).** "
             f"Valid analysis {pct(rep['valid_rate'])}.", "", "| type | recall | misses |", "|---|---|---|"]
    lines += [f"| {t} | {pct(v)} | {rep['missed_by_type'].get(t, 0)} |" for t, v in rep["recall_by_type"].items()]
    lines += ["", "## Values missed (times out of rounds)", ""]
    lines += [f"- `{m['id']}` · **{m['value']}** · {m['times']}/{rep['rounds']}" for m in rep["consistent_misses"]] or ["- none"]
    lines += ["", "## Per example (last round)", ""]
    last = [r for r in rep["rows"] if r["round"] == rep["rounds"]]
    for r in last:
        lines += [f"### {r['id']}", "",
                  f"- missed: {', '.join(m['value'] for m in r['missed']) or 'none'}",
                  f"- partly covered: {', '.join(f'{p['value']} ({p['covered']:.0%})' for p in r['partial']) or 'none'}",
                  f"- type mismatches: {', '.join(f'{w['value']} {w['expected']}→{w['got']}' for w in r['wrong_type']) or 'none'}",
                  f"- optional masked: {', '.join(k for k, v in r['optional_masked'].items() if v) or 'none'}; "
                  f"left visible: {', '.join(k for k, v in r['optional_masked'].items() if not v) or 'none'}",
                  f"- must stay readable: {', '.join(f'{k} ({'kept' if v else 'MASKED'})' for k, v in r['kept'].items()) or 'n/a'}",
                  f"- extra masked: {', '.join(r['extra_masked']) or 'none'}",
                  f"- contexts: {', '.join(r['contexts']) or 'none'} (expected {', '.join(r['contexts_expected']) or 'none'})",
                  "", "```", r["masked_text"], "```", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.realistic")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--tag", default="realistic10")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args(argv)
    rep = run(args.rounds)
    md = render(rep)
    print("\n" + md)
    if not args.no_record:
        from .results import save_run

        summary = {"backend": "muse_spark", "model": rep["model"], "docs": rep["examples"] * rep["rounds"],
                   "leak_rate": rep["leak_rate"], "span_recall": rep["span_recall"], "valid_rate": rep["valid_rate"],
                   "recall_by_type": rep["recall_by_type"], "cost_usd": rep["cost_usd"], "seconds": rep["seconds"],
                   "cost": {"usd": rep["cost_usd"], "basis": "tokens"}, "consistent_misses": rep["consistent_misses"]}
        out = save_run("realistic-pii", args.tag, [summary], {"muse_spark": rep["rows"]}, compare_md=md,
                       settings={"muse_spark": {"model": rep["model"], "reasoning_effort": rep["reasoning_effort"], "rounds": rep["rounds"]}},
                       dataset={"name": "muse_shield.realistic", "docs": rep["examples"], "rounds": rep["rounds"]})
        print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
