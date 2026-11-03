"""Six realistic multi-turn conversations (1 general + 5 sectors), the way people actually talk to a chat
assistant: long, messy, and full of the names, numbers and confidential context they shouldn't be pasting.

    MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.conversations --rounds 2
    .venv/bin/python -m muse_shield.conversations --print          # dump the turns to paste into the UI

Each conversation is one chat: every turn goes through call 1 in the same chat, so a person named in turn 1
should get the same placeholder when they come back in turn 3. Every value is invented.

Per turn (same scoring as `realistic.py`):
    must      values that must not reach the chat model
    optional  borderline values: reported, not scored
    keep      the user's actual question, which must stay readable
    contexts  context-block kinds we expect (reported)

Per conversation:
    same      values that recur (across turns or inside one): all their placeholders must agree
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
from .realistic import Example, score


@dataclass
class Turn:
    text: str
    must: list[tuple[str, str]]
    optional: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)


@dataclass
class Conversation:
    id: str
    sector: str
    title: str
    turns: list[Turn]
    same: list[str] = field(default_factory=list)


CONVERSATIONS = [
    Conversation("general-wedding-move", "general", "Wedding, a flat and a sensitive family note", [
        Turn("""Hey, I need help planning the next 3 months. I'm Nikhil Deshpande, getting married to Shreya Kulkarni on 21 Feb 2027 at Taj Fort Aguada, Goa. Her parents (Mr. Suresh and Mrs. Latha Kulkarni) are paying for the venue, we're paying for the rest. Our budget is ₹22 lakh total. I've got ₹9 lakh saved in my Kotak account (acct 8811234567) and Shreya has about ₹6 lakh. Can you make me a month-by-month plan with what to book first?""",
             must=[("Nikhil Deshpande", "PERSON"), ("Shreya Kulkarni", "PERSON"), ("Latha Kulkarni", "PERSON"), ("₹22 lakh", "AMOUNT"),
                   ("₹9 lakh", "AMOUNT"), ("8811234567", "ID"), ("₹6 lakh", "AMOUNT")],
             optional=["Suresh", "21 Feb 2027", "Taj Fort Aguada, Goa", "Kotak"],
             keep=["month-by-month plan with what to book first"]),
        Turn("""Also we're moving in together after. Found a 2BHK at Flat 7C, Sunshine Towers, Baner, Pune 411045, rent ₹38,000. The landlord is Mrs. Pushpa Joshi, 98500 11223, she wants a copy of my Aadhaar (4512 8899 0021) and my company ID letter from Persistent Systems for the police verification. Is it normal to share Aadhaar with a landlord? What should I black out?""",
             must=[("Flat 7C, Sunshine Towers, Baner, Pune 411045", "ADDRESS"), ("₹38,000", "AMOUNT"), ("Pushpa Joshi", "PERSON"),
                   ("98500 11223", "CONTACT"), ("4512 8899 0021", "ID")],
             optional=["Persistent Systems"],
             keep=["Is it normal to share Aadhaar with a landlord"]),
        Turn("""One more thing, sensitive. Shreya's brother Aniket has been in rehab for alcohol addiction since August and her parents don't want it mentioned at the wedding. He's also diabetic. Can you help me write a note to the caterer (Rohan at feast.goa@gmail.com) asking for a no-alcohol, sugar-free table for a few guests without saying why? And remind me to repay the ₹1.5 lakh I borrowed from my friend Varun before the wedding.""",
             must=[("Aniket", "PERSON"), ("rehab for alcohol addiction", "SENSITIVE_ATTRIBUTE"), ("diabetic", "SENSITIVE_ATTRIBUTE"),
                   ("Rohan", "PERSON"), ("feast.goa@gmail.com", "CONTACT"), ("₹1.5 lakh", "AMOUNT"), ("Varun", "PERSON")],
             optional=["August"],
             keep=["no-alcohol, sugar-free table"]),
    ], same=["Shreya"]),

    Conversation("finance-wealth-review", "finance", "Wealth advisor: client review, divorce, asset shuffle", [
        Turn("""I'm preparing the quarterly review for my client Mr. Rajiv Khanna (PAN AFZPK3321Q, client code WM-10928). Portfolio as of 30 Sep: ₹4.6 crore in equity MFs, ₹1.2 crore in direct stocks (demat 1208870012345678 with Zerodha), ₹85 lakh FDs at HDFC, and ₹2.3 crore in a commercial property at Unit 401, Prestige Trade Tower, MG Road, Bengaluru 560001 that gives ₹1.4 lakh/month rent. He has a ₹60 lakh loan against property with Bajaj at 9.1%. Summarize this into a one-page allocation view and flag concentration risk.""",
             must=[("Rajiv Khanna", "PERSON"), ("AFZPK3321Q", "ID"), ("WM-10928", "ID"), ("₹4.6 crore", "AMOUNT"), ("₹1.2 crore", "AMOUNT"),
                   ("1208870012345678", "ID"), ("₹85 lakh", "AMOUNT"), ("₹2.3 crore", "AMOUNT"),
                   ("Unit 401, Prestige Trade Tower, MG Road, Bengaluru 560001", "ADDRESS"), ("₹1.4 lakh", "AMOUNT"), ("₹60 lakh", "AMOUNT")],
             optional=["30 Sep", "Zerodha", "HDFC", "Bajaj", "9.1%"],
             keep=["flag concentration risk"]),
        Turn("""Context you need: Rajiv is going through a divorce. His wife Meenakshi Khanna's lawyer has asked for full disclosure and Rajiv wants to move ₹1.5 crore into his mother's name (Kamla Khanna, PAN AKDPK9087R) before the petition is filed on 15 Dec. I told him I can't advise on hiding assets. He also mentioned he's being treated for depression and doesn't want it in any file. What's the compliant way to document this conversation for our records, and what do I need to escalate to compliance?""",
             must=[("Rajiv", "PERSON"), ("Meenakshi Khanna", "PERSON"), ("₹1.5 crore", "AMOUNT"), ("Kamla Khanna", "PERSON"),
                   ("AKDPK9087R", "ID"), ("depression", "SENSITIVE_ATTRIBUTE")],
             optional=["going through a divorce", "15 Dec"],
             keep=["what do I need to escalate to compliance"], contexts=["PLAN", "DECISION"]),
        Turn("""Draft the email to him. His email is rajiv.khanna72@gmail.com, cc his CA Prakash Iyer (prakash@iyerandco.in). Mention the SIP of ₹2 lakh/month continues, that the FD maturing on 12 Jan (₹25 lakh) should roll over, and that his daughter Tara's education fund (₹40 lakh target by 2030) is on track. Keep it warm but formal, no mention of the divorce.""",
             must=[("rajiv.khanna72@gmail.com", "CONTACT"), ("Prakash Iyer", "PERSON"), ("prakash@iyerandco.in", "CONTACT"),
                   ("₹2 lakh", "AMOUNT"), ("₹25 lakh", "AMOUNT"), ("Tara", "PERSON"), ("₹40 lakh", "AMOUNT")],
             optional=["12 Jan", "2030"],
             keep=["Keep it warm but formal"]),
    ], same=["Rajiv"]),

    Conversation("health-discharge", "healthcare", "Discharge summary, referral and an HIV disclosure question", [
        Turn("""Help me write a discharge summary. Patient Fatima Sheikh, 34F, DOB 02/11/1992, MRN KH-558201, admitted 28 Oct 2026 at Kokilaben Hospital under Dr. Anand Mehta (Reg. no. MMC 45678). Admitted with preeclampsia at 32 weeks of pregnancy, BP 160/110 on arrival. She is HIV positive, on tenofovir/lamivudine/dolutegravir, viral load undetectable. Managed with labetalol 100 mg BD and magnesium sulfate. Delivered a healthy baby girl by emergency C-section on 30 Oct, 1.8 kg. Discharged 3 Nov on labetalol 100 mg BD.""",
             must=[("Fatima Sheikh", "PERSON"), ("02/11/1992", "DATE"), ("KH-558201", "ID"), ("Anand Mehta", "PERSON"), ("MMC 45678", "ID"),
                   ("preeclampsia", "SENSITIVE_ATTRIBUTE"), ("32 weeks of pregnancy", "SENSITIVE_ATTRIBUTE"), ("HIV positive", "SENSITIVE_ATTRIBUTE")],
             optional=["28 Oct 2026", "Kokilaben Hospital", "tenofovir/lamivudine/dolutegravir", "labetalol 100 mg", "emergency C-section", "30 Oct", "3 Nov"],
             keep=["discharge summary"]),
        Turn("""Her follow-up: she lives at 12/3 Bismillah Chawl, Behrampada, Bandra East, Mumbai 400051, phone 98201 77654, husband Imran Sheikh (alternate contact 98201 77655). She has no insurance; the bill of ₹3,84,000 was partly covered by the hospital's charity fund, balance ₹1,20,000 outstanding. Her sister Nasreen is a nurse at Sion Hospital and will help with home BP monitoring. Please also draft a referral letter to Dr. Priya Nambiar, ART centre at JJ Hospital (priya.nambiar@jjhospital.org) for the infant's PCR test at 6 weeks.""",
             must=[("12/3 Bismillah Chawl, Behrampada, Bandra East, Mumbai 400051", "ADDRESS"), ("98201 77654", "CONTACT"), ("Imran Sheikh", "PERSON"),
                   ("98201 77655", "CONTACT"), ("₹3,84,000", "AMOUNT"), ("₹1,20,000", "AMOUNT"), ("Nasreen", "PERSON"),
                   ("Priya Nambiar", "PERSON"), ("priya.nambiar@jjhospital.org", "CONTACT")],
             optional=["Sion Hospital", "JJ Hospital", "6 weeks"],
             keep=["draft a referral letter"]),
        Turn("""Patient asked that her HIV status NOT be mentioned in the copy given to her employer (she works as a housekeeper for a family in Pali Hill, the Malhotras) because she's afraid of losing the job. Can I legally leave it out of the fit-to-work certificate? What should the certificate say instead? Also her login for the hospital portal is fatima.s92 / Baby@2026, can you tell her how to change it, she's not tech savvy.""",
             must=[("HIV status", "SENSITIVE_ATTRIBUTE"), ("Malhotras", "PERSON"), ("fatima.s92", "ID"), ("Baby@2026", "SECRET")],
             optional=["Pali Hill", "housekeeper"],
             keep=["Can I legally leave it out of the fit-to-work certificate"]),
    ], same=[]),

    Conversation("legal-settlement-nda", "legal", "Settlement draft, privileged strategy, a new-client NDA", [
        Turn("""I'm an associate at Desai & Partners. Need a first draft of a settlement agreement. Matter: Vikrant Textiles Pvt Ltd v. Sameer Chawla, Commercial Suit No. 1187/2025, Bombay High Court. Our client Vikrant (MD: Mr. Harish Vikrant) sued their ex-CFO Sameer Chawla for diverting ₹3.2 crore to a shell company, Meridian Trading LLP. Opposing counsel is Advocate Rukmini Pillai of Pillai Law Chambers. Settlement terms agreed in mediation on 29 Oct: Chawla repays ₹2.1 crore in 3 instalments, first ₹70 lakh within 30 days into escrow at Axis Bank A/c 917010045612345 (IFSC UTIB0000123), mutual non-disparagement, and we withdraw the criminal complaint FIR No. 0421/2025 at Worli PS.""",
             must=[("Vikrant Textiles Pvt Ltd", "ORG"), ("Sameer Chawla", "PERSON"), ("1187/2025", "ID"), ("Harish Vikrant", "PERSON"),
                   ("₹3.2 crore", "AMOUNT"), ("Meridian Trading LLP", "ORG"), ("Rukmini Pillai", "PERSON"), ("Pillai Law Chambers", "ORG"),
                   ("₹2.1 crore", "AMOUNT"), ("₹70 lakh", "AMOUNT"), ("917010045612345", "ID"), ("UTIB0000123", "ID"), ("0421/2025", "ID")],
             optional=["Desai & Partners", "Bombay High Court", "29 Oct", "Axis Bank", "Worli PS"],
             keep=["first draft of a settlement agreement"], contexts=["DEAL", "NEGOTIATION"]),
        Turn("""Privileged strategy, keep this separate from the draft: the partner, Ms. Anjali Desai, thinks Chawla will default on the second instalment because his flat at 904, Oberoi Springs, Andheri West is already mortgaged for ₹1.8 crore to Kotak. She wants a personal guarantee from his wife, Dr. Neha Chawla (a dentist, clinic at Lokhandwala), and a post-dated cheque. Our client's internal cap is ₹1.9 crore — do not reveal this to the other side. Also, the client's own auditor flagged that Harish Vikrant himself approved two of the diverted payments, which weakens our fraud claim. Give me a negotiation plan for the call with Pillai tomorrow.""",
             must=[("Anjali Desai", "PERSON"), ("Chawla", "PERSON"), ("904, Oberoi Springs, Andheri West", "ADDRESS"), ("₹1.8 crore", "AMOUNT"),
                   ("Neha Chawla", "PERSON"), ("₹1.9 crore", "AMOUNT"), ("Harish Vikrant", "PERSON"), ("Pillai", "PERSON")],
             optional=["Kotak", "Lokhandwala", "dentist"],
             keep=["Give me a negotiation plan"], contexts=["NEGOTIATION", "DECISION"]),
        Turn("""Separately draft an NDA for a new client: Zephyr Biotech Ltd (CIN U24230MH2019PLC334455), signatory Dr. Kabir Sethi, CEO, kabir@zephyrbio.com, +91 98211 44556, registered office at 7th Floor, Nirlon Knowledge Park, Goregaon East, Mumbai 400063. Counterparty: Helix Ventures (Singapore), signatory Ms. Wei Lin Tan. Purpose: evaluating a Series A of USD 12 million at a USD 48 million pre-money. Term 2 years, Mumbai jurisdiction. Standard mutual NDA, nothing fancy.""",
             must=[("Zephyr Biotech Ltd", "ORG"), ("U24230MH2019PLC334455", "ID"), ("Kabir Sethi", "PERSON"), ("kabir@zephyrbio.com", "CONTACT"),
                   ("+91 98211 44556", "CONTACT"), ("7th Floor, Nirlon Knowledge Park, Goregaon East, Mumbai 400063", "ADDRESS"),
                   ("Helix Ventures", "ORG"), ("Wei Lin Tan", "PERSON"), ("USD 12 million", "AMOUNT"), ("USD 48 million", "AMOUNT")],
             optional=["Singapore", "2 years"],
             keep=["Standard mutual NDA"], contexts=["DEAL"]),
    ], same=["Sameer Chawla", "Harish Vikrant"]),

    Conversation("hr-offer-complaint-layoffs", "hr", "An offer with a background flag, a POSH complaint, a layoff list", [
        Turn("""I'm the hiring manager for the Senior Data Engineer role at Quantiva Analytics. Finalizing an offer for Priyanka Raghavan (priyanka.r88@gmail.com, 97400 12398). Her current CTC at Mu Sigma is ₹32 lakh, she's asking ₹45 lakh, our band tops out at ₹42 lakh and I have approval from the VP, Deepak Sharma, for ₹41 lakh + ₹3 lakh joining bonus. Background check from AuthBridge came back with one flag: a 2019 cheque bounce case (CC No. 2231/2019, Bengaluru) that was later settled. She also disclosed she's 5 months pregnant and will need leave from March. Draft the offer letter and tell me how to handle the pregnancy and the background flag legally.""",
             must=[("Quantiva Analytics", "ORG"), ("Priyanka Raghavan", "PERSON"), ("priyanka.r88@gmail.com", "CONTACT"), ("97400 12398", "CONTACT"),
                   ("₹32 lakh", "AMOUNT"), ("₹45 lakh", "AMOUNT"), ("₹42 lakh", "AMOUNT"), ("Deepak Sharma", "PERSON"), ("₹41 lakh", "AMOUNT"),
                   ("₹3 lakh", "AMOUNT"), ("2231/2019", "ID"), ("5 months pregnant", "SENSITIVE_ATTRIBUTE")],
             optional=["Mu Sigma", "AuthBridge", "cheque bounce case", "March"],
             keep=["Draft the offer letter"], contexts=["HR", "DECISION"]),
        Turn("""Different issue, confidential. An employee on my team, Manoj Pillai (EMP-3391), filed a POSH complaint against his manager Ritesh Agarwal (EMP-1120) on 27 Oct — alleges Ritesh made comments about his sexuality in two team meetings and denied him the Q3 promotion. The IC chair is Sunita Rao. Ritesh is up for a ₹12 lakh retention bonus in Dec which I'm now supposed to put on hold. Manoj's personal email is manoj.pillai@protonmail.com and he's asked that HR not use his office email. What are my obligations as his skip-level, and what should I NOT do or say?""",
             must=[("Manoj Pillai", "PERSON"), ("EMP-3391", "ID"), ("Ritesh Agarwal", "PERSON"), ("EMP-1120", "ID"), ("his sexuality", "SENSITIVE_ATTRIBUTE"),
                   ("Sunita Rao", "PERSON"), ("₹12 lakh", "AMOUNT"), ("manoj.pillai@protonmail.com", "CONTACT")],
             optional=["27 Oct", "Q3", "Dec"],
             keep=["What are my obligations as his skip-level"], contexts=["HR"]),
        Turn("""Last: layoffs. Finance wants 8 of my 31 people gone by 31 Dec to save ₹2.4 crore annually. My list so far: Arjun Nair (₹28L, low performer), Sneha Patil (₹22L, on maternity leave till Feb — can we even?), Tom Varghese (₹35L, visa H-1B sponsor transfer pending, he's in the US office), and Kavita Bhat (₹19L, 58 years old). Give me a fair selection framework and tell me which of these picks are legally risky in India and the US.""",
             must=[("₹2.4 crore", "AMOUNT"), ("Arjun Nair", "PERSON"), ("₹28L", "AMOUNT"), ("Sneha Patil", "PERSON"), ("₹22L", "AMOUNT"),
                   ("on maternity leave", "SENSITIVE_ATTRIBUTE"), ("Tom Varghese", "PERSON"), ("₹35L", "AMOUNT"), ("Kavita Bhat", "PERSON"), ("₹19L", "AMOUNT")],
             optional=["31 Dec", "Feb", "H-1B", "58 years old", "low performer"],
             keep=["fair selection framework"], contexts=["HR", "PLAN", "DECISION"]),
    ], same=["Ritesh", "Manoj"]),

    Conversation("tech-outage-breach-bridge", "tech", "Outage RCA, leaked keys and a bridge-round disclosure", [
        Turn("""I'm CTO at Lumio Health (Series A, 40 people). Our biggest customer Apollo Diagnostics (contract ₹1.8 crore/yr, renews 31 Mar) is threatening to churn after Sunday's outage. Their CTO Vivek Menon (vivek.menon@apollodx.com) wants an RCA by Friday. Here's what happened: at 02:14 IST a deploy by our SRE Lakshmi Iyer bumped the Postgres pool and we hit max connections on db-primary.lumio.internal (10.20.3.11). The postmortem Slack thread has the connection string in it: postgres://lumio_app:Lum10!Pr0d2026@db-primary.lumio.internal:5432/lumio. Write me a customer-facing RCA that's honest but doesn't name the engineer.""",
             must=[("Lumio Health", "ORG"), ("Apollo Diagnostics", "ORG"), ("₹1.8 crore", "AMOUNT"), ("Vivek Menon", "PERSON"),
                   ("vivek.menon@apollodx.com", "CONTACT"), ("Lakshmi Iyer", "PERSON"), ("10.20.3.11", "ID"), ("Lum10!Pr0d2026", "SECRET")],
             optional=["31 Mar", "Sunday", "Friday", "02:14 IST", "db-primary.lumio.internal", "lumio_app"],
             keep=["customer-facing RCA"], contexts=["DEAL"]),
        Turn("""While fixing it we found worse: a Jupyter notebook in the repo with hardcoded creds. AWS AKIA3XAMPLEKEY9Q7Z2W / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY, a Twilio token SK9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c, and a Razorpay key rzp_live_H7qK2mNvX4pLwR. Also patient records from Apollo (names + Aadhaar) were in an S3 bucket lumio-ml-scratch set to public-read since July. Our DPO is Farah Khan (farah@lumio.health). Under DPDP Act do we have to notify CERT-In and the patients, and in what timeline? Draft the internal incident note.""",
             must=[("AKIA3XAMPLEKEY9Q7Z2W", "SECRET"), ("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "SECRET"),
                   ("SK9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c", "SECRET"), ("rzp_live_H7qK2mNvX4pLwR", "SECRET"), ("Farah Khan", "PERSON"), ("farah@lumio.health", "CONTACT")],
             optional=["lumio-ml-scratch", "July", "Apollo"],
             keep=["do we have to notify CERT-In"]),
        Turn("""Investor side, strictly confidential: our lead, Nandini Rao at Peak XV, knows about the outage but not the bucket. We have ₹14 crore in the bank, burn is ₹1.1 crore/month, and the bridge round (₹20 crore at ₹160 crore pre) is supposed to close 20 Dec. The CEO, Siddharth Jain, wants to delay telling her until after the term sheet is signed. I think that's a disclosure problem. Help me write a 5-line message to Siddharth making the case, and a separate neutral update for Nandini if he agrees.""",
             must=[("Nandini Rao", "PERSON"), ("Peak XV", "ORG"), ("₹14 crore", "AMOUNT"), ("₹1.1 crore", "AMOUNT"), ("₹20 crore", "AMOUNT"),
                   ("₹160 crore", "AMOUNT"), ("Siddharth Jain", "PERSON")],
             optional=["20 Dec"],
             keep=["5-line message"], contexts=["DEAL", "DECISION"]),
    ], same=["Apollo", "Siddharth", "Nandini"]),
]


def placeholders_for(value: str, text: str, spans: list[dict]) -> set[str]:
    """Every entity placeholder covering an occurrence of `value` in `text` (at least half of it). Context blocks don't count: a name inside one keeps its own placeholder."""
    out: set[str] = set()
    i = text.find(value)
    while i >= 0:
        end = i + len(value)
        for s in spans:
            if s["kind"] != "entity":
                continue
            overlap = min(end, s["end"]) - max(i, s["start"])
            if overlap * 2 >= len(value):
                out.add(s["placeholder"])
        i = text.find(value, end)
    return out


def run(rounds: int = 2, conversations: list[Conversation] = CONVERSATIONS, analyzer=None) -> dict:
    analyzer = analyzer or analyzer_from_env()[0]
    if analyzer is None:
        raise SystemExit("analysis is off: " + analyzer_from_env()[1])
    t0 = time.perf_counter()
    rows, links = [], []
    for r in range(1, rounds + 1):
        vault = Vault(":memory:", os.urandom(32))  # fresh vault per round
        masker = Masker(vault, analyzer)
        for conv in conversations:
            chat = vault.create_chat()  # one chat per conversation: placeholders carry across turns
            seen: dict[str, set[str]] = defaultdict(set)
            for n, turn in enumerate(conv.turns, 1):
                ex = Example(f"{conv.id}/t{n}", conv.title, turn.text, turn.must, turn.optional, turn.keep, turn.contexts)
                res = masker.mask(turn.text, chat)
                row = score(ex, res) | {"round": r, "conversation": conv.id, "sector": conv.sector, "turn": n}
                rows.append(row)
                for v in conv.same:
                    seen[v] |= placeholders_for(v, turn.text, res.spans)
                leaks = ", ".join(m["value"] for m in row["missed"]) or "none"
                print(f"round {r} · {conv.id:28} t{n} missed {len(row['missed'])}/{row['must']}: {leaks}", flush=True)
            for v in conv.same:
                links.append({"round": r, "conversation": conv.id, "value": v, "placeholders": sorted(seen[v]),
                              "linked": len(seen[v]) == 1, "unmasked": len(seen[v]) == 0})

    must_total = sum(r["must"] for r in rows)
    missed_total = sum(len(r["missed"]) for r in rows)
    by_type_total, by_type_missed = Counter(), Counter()
    for conv in conversations:
        for turn in conv.turns:
            for _, t in turn.must:
                by_type_total[t] += rounds
    miss_count: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        for m in r["missed"]:
            by_type_missed[m["type"]] += 1
            miss_count[(r["id"], m["value"])] += 1
    by_sector: dict[str, dict] = {}
    for r in rows:
        s = by_sector.setdefault(r["sector"], {"must": 0, "missed": 0, "extra": 0, "cost_usd": 0.0, "latency_ms": []})
        s["must"] += r["must"]
        s["missed"] += len(r["missed"])
        s["extra"] += len(r["extra_masked"])
        s["cost_usd"] += r["cost_usd"]
        s["latency_ms"].append(r["latency_ms"])
    for s in by_sector.values():
        s["latency_ms"] = round(sum(s["latency_ms"]) / len(s["latency_ms"]))
        s["cost_usd"] = round(s["cost_usd"], 5)
    return {
        "rounds": rounds, "conversations": len(conversations), "turns": sum(len(c.turns) for c in conversations),
        "seconds": round(time.perf_counter() - t0, 1),
        "model": getattr(analyzer, "model", "?"), "reasoning_effort": getattr(analyzer, "extra", {}).get("reasoning_effort"),
        "must_total": must_total, "missed_total": missed_total,
        "leak_rate": missed_total / must_total if must_total else None,
        "span_recall": 1 - missed_total / must_total if must_total else None,
        "valid_rate": sum(r["ok"] for r in rows) / len(rows),
        "recall_by_type": {t: 1 - by_type_missed[t] / n for t, n in sorted(by_type_total.items())},
        "missed_by_type": dict(by_type_missed),
        "by_sector": by_sector,
        "consistent_misses": sorted([{"id": k[0], "value": k[1], "times": v} for k, v in miss_count.items()], key=lambda x: -x["times"]),
        "links": links, "linked_rate": sum(l["linked"] for l in links) / len(links) if links else None,
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 5),
        "rows": rows,
    }


def render(rep: dict) -> str:
    pct = lambda x: "–" if x is None else f"{x:.1%}"  # noqa: E731
    lines = [f"# Realistic conversations · {rep['conversations']} chats, {rep['turns']} turns × {rep['rounds']} rounds",
             "", f"model `{rep['model']}` (reasoning {rep['reasoning_effort']}) · {rep['seconds']}s · ${rep['cost_usd']:.4f}", "",
             f"**Missed {rep['missed_total']} of {rep['must_total']} must-mask values ({pct(rep['leak_rate'])} leak).** "
             f"Valid analysis {pct(rep['valid_rate'])}. Recurring values linked to one placeholder: {pct(rep['linked_rate'])}.", "",
             "| sector | must | missed | extra masked | avg latency | cost |", "|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['must']} | {v['missed']} | {v['extra']} | {v['latency_ms']} ms | ${v['cost_usd']:.4f} |" for k, v in rep["by_sector"].items()]
    lines += ["", "| type | recall | misses |", "|---|---|---|"]
    lines += [f"| {t} | {pct(v)} | {rep['missed_by_type'].get(t, 0)} |" for t, v in rep["recall_by_type"].items()]
    lines += ["", "## Values missed (times out of rounds)", ""]
    lines += [f"- `{m['id']}` · **{m['value']}** · {m['times']}/{rep['rounds']}" for m in rep["consistent_misses"]] or ["- none"]
    lines += ["", "## Linking: the same value across turns", ""]
    for l in rep["links"]:
        state = "unmasked" if l["unmasked"] else ("ok" if l["linked"] else "SPLIT")
        lines.append(f"- round {l['round']} · `{l['conversation']}` · **{l['value']}** → {', '.join(l['placeholders']) or '—'} ({state})")
    lines += ["", "## Per turn (last round)", ""]
    for r in [r for r in rep["rows"] if r["round"] == rep["rounds"]]:
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
    ap = argparse.ArgumentParser(prog="python -m muse_shield.conversations")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--tag", default="conversations6")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--print", action="store_true", help="print the turns (to paste into the UI) and exit")
    args = ap.parse_args(argv)
    if args.print:
        for c in CONVERSATIONS:
            print(f"\n===== {c.sector}: {c.title} =====")
            for n, t in enumerate(c.turns, 1):
                print(f"\n--- turn {n} ---\n{t.text}")
        return 0
    rep = run(args.rounds)
    md = render(rep)
    print("\n" + md)
    if not args.no_record:
        from .results import save_run

        summary = {"backend": "muse_spark", "model": rep["model"], "docs": rep["turns"] * rep["rounds"],
                   "leak_rate": rep["leak_rate"], "span_recall": rep["span_recall"], "valid_rate": rep["valid_rate"],
                   "linked_rate": rep["linked_rate"], "recall_by_type": rep["recall_by_type"], "by_sector": rep["by_sector"],
                   "cost_usd": rep["cost_usd"], "seconds": rep["seconds"], "cost": {"usd": rep["cost_usd"], "basis": "tokens"},
                   "consistent_misses": rep["consistent_misses"], "links": rep["links"]}
        out = save_run("realistic-conversations", args.tag, [summary], {"muse_spark": rep["rows"]}, compare_md=md,
                       settings={"muse_spark": {"model": rep["model"], "reasoning_effort": rep["reasoning_effort"], "rounds": rep["rounds"]}},
                       dataset={"name": "muse_shield.conversations", "conversations": rep["conversations"], "turns": rep["turns"], "rounds": rep["rounds"]})
        print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
