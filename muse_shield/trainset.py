"""Fine-tuning data for Muse Glimmer: chat JSONL in exactly the runtime prompt format.

    .venv/bin/python -m muse_shield.trainset --n 600 --out runs/train

Each row is the same messages GlimmerBackend sends (system prompt, the one
worked example, the numbered paragraph) plus the gold JSON as the assistant
turn. Fillers come from TRAIN_POOLS, which share no names, orgs, places or
amounts with the eval set, and the eval-only acceptance case is excluded, so
before/after eval scores measure generalization rather than memorization.
Everything is synthetic.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .analysis import number_sentences, parse
from .backends import EXAMPLE_ASSISTANT, EXAMPLE_USER, SYSTEM_PROMPT
from .evalset import EVAL_POOLS, Case, Pools, generate

TRAIN_POOLS = Pools(
    people=["Aditi Kulkarni", "Siddharth Menon", "Neha Joshi", "Rahul Verma", "Tanvi Desai", "Karthik Subramanian",
            "Zoya Siddiqui", "Manish Agarwal", "Pooja Hegde", "Nikhil Bhat", "Ritika Sen", "Omar Sheikh",
            "Grace Thomas", "Mateo Silva", "Lakshmi", "Varun"],
    orgs=["Peregrine Systems", "Saffron Foods", "Bluepeak Analytics", "Ironleaf Motors", "Coralstone Media",
          "Amberline Pharma", "Riverbend Textiles"],
    banks=["Deccan Rural Bank", "Konkan Credit Union", "Meridian Housing Finance"],
    cities=["Guntur", "Thrissur", "Nashik", "Madurai", "Bhopal", "Udaipur", "Hubballi"],
    addresses=["8-2-293, Road No. 5, Guntur", "House 14, Temple Street, Madurai", "B-17, Shanti Nagar, Bhopal",
               "Villa 3, Palm Grove Layout, Hubballi", "221 Station Road, Nashik"],
    codenames=["Project Peacock", "Project Tamarind", "Project Nilgiri", "Project Ganga"],
    salaries=["9 lakh rupees", "16.5 lakh rupees", "₹32 lakh a year", "7.5 LPA", "₹1.1 crore a year"],
    prices=["₹28,500", "₹1.8 lakh", "4,20,000 rupees", "₹950"],
    loans=["30 lakh", "₹55 lakh", "5 lakh rupees", "₹1.2 crore"],
    deals=["₹300 crore", "$450M", "₹18 crore", "$2.1B"],
    budgets=["₹75 lakh", "40 lakh rupees", "₹3.5 crore"],
)

# Gold subtype and a names-free, numbers-free summary per template, per the contract.
TEMPLATE_CONTEXT = {
    "acceptance": ("PURCHASE", "plans to buy land"),
    "salary_decision": ("PURCHASE", "plans to buy a flat"),
    "deal": ("ACQUISITION", "company acquisition with due diligence"),
    "negotiation": ("SALARY", "salary negotiation before signing"),
    "hr": ("TERMINATION", "employee being let go"),
    "project": ("LAUNCH", "product launch with approved budget"),
    "plan": ("EXPANSION", "opening a new office"),
}


def _overlap(a: Pools, b: Pools) -> set[str]:
    return {v for f in a.__dataclass_fields__ for v in getattr(a, f)} & {v for f in b.__dataclass_fields__ for v in getattr(b, f)}


def gold_json(case: Case) -> str:
    subtype, summary = TEMPLATE_CONTEXT.get(case.template, (None, ""))
    entities = []
    for e in case.entities:
        item = {"text": e.text, "type": e.type}
        if e.role:
            item["role"] = e.role
        entities.append(item)
    contexts = [{"sentences": c.sentences, "kind": c.kind, "subtype": subtype, "refers_to": None, "summary": summary}
                for c in case.contexts]
    return json.dumps({"entities": entities, "contexts": contexts}, ensure_ascii=False)


def row(case: Case) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": EXAMPLE_USER},
        {"role": "assistant", "content": EXAMPLE_ASSISTANT},
        {"role": "user", "content": f"Known contexts: none\n{number_sentences(case.sentences)}"},
        {"role": "assistant", "content": gold_json(case)},
    ]}


def build(n: int = 600, seed: int = 101) -> list[dict]:
    if _overlap(TRAIN_POOLS, EVAL_POOLS):
        raise ValueError(f"train and eval pools overlap: {_overlap(TRAIN_POOLS, EVAL_POOLS)}")
    # generate() always puts the eval-only acceptance case first; drop it.
    cases = [c for c in generate(n + 1, seed, TRAIN_POOLS) if c.template != "acceptance"][:n]
    rows = []
    for c in cases:
        r = row(c)
        a = parse(r["messages"][-1]["content"], c.paragraph, c.sentences)  # every gold row must pass the contract
        assert not a.dropped, c.id
        rows.append(r)
    random.Random(seed).shuffle(rows)
    return rows


def export(out: Path, n: int = 600, seed: int = 101, val_fraction: float = 0.1) -> dict:
    rows = build(n, seed)
    k = max(1, int(len(rows) * val_fraction))
    out.mkdir(parents=True, exist_ok=True)
    for name, chunk in (("val", rows[:k]), ("train", rows[k:])):
        with (out / f"{name}.jsonl").open("w") as f:
            for r in chunk:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    longest = max(sum(len(m["content"]) for m in r["messages"]) for r in rows)
    return {"train": len(rows) - k, "val": k, "dir": str(out), "longest_row_chars": longest,
            "approx_longest_row_tokens": longest // 3}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.trainset")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--out", type=Path, default=Path("runs/train"))
    args = ap.parse_args(argv)
    print(json.dumps(export(args.out, args.n, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
