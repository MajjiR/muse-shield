"""Fine-tuning data for Muse Glimmer: chat JSONL in exactly the runtime prompt format.

    .venv/bin/python -m muse_shield.trainset --n 600 --out runs/train
    .venv/bin/python -m muse_shield.trainset --mix --out runs/train/mix-v1   # Nemotron train + synthetic

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

from .analysis import number_sentences, parse, split_sentences
from .backends import EXAMPLE_ASSISTANT, EXAMPLE_USER, SYSTEM_PROMPT
from .benchmarks.nemotron import LABEL_MAP, SPLIT_ROWS, Doc, _fetch_page, paragraphs, parse_row
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


def chat_row(sentences: list[str], answer: str) -> dict:
    """One training row in exactly the message layout GlimmerBackend sends at runtime."""
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": EXAMPLE_USER},
        {"role": "assistant", "content": EXAMPLE_ASSISTANT},
        {"role": "user", "content": f"Known contexts: none\n{number_sentences(sentences)}"},
        {"role": "assistant", "content": answer},
    ]}


def row(case: Case) -> dict:
    return chat_row(case.sentences, gold_json(case))


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
        r["_meta"] = {"source": "synthetic", "domain": f"synthetic:{c.template}", "approx_tokens": _approx_tokens(r)}
        rows.append(r)
    random.Random(seed).shuffle(rows)
    return rows


def _approx_tokens(r: dict) -> int:
    return sum(len(m["content"]) for m in r["messages"]) // 3  # conservative chars-per-token


def benchmark_paragraphs(test_sample: Path) -> set[str]:
    """Every paragraph of the benchmark's test docs: training must never contain one."""
    docs = [Doc.from_dict(json.loads(l)) for l in test_sample.read_text().splitlines() if l.strip()]
    return {p for d in docs for _, p in paragraphs(d.text)}


def nemotron_rows(n: int, seed: int, exclude: set[str], fetch=_fetch_page, pages: int = 30,
                  max_tokens: int = 2048, empty_share: float = 0.15) -> list[dict]:
    """Gold-labelled rows from the Nemotron-PII *train* split, one per paragraph.

    Paragraphs are cut exactly as the benchmark cuts them, and gold labels are mapped onto
    contract types with the benchmark's LABEL_MAP. Nemotron has no context labels, so
    `contexts` is empty; the synthetic rows carry contexts. A gold span that crosses a
    paragraph boundary is skipped rather than guessed.
    """
    rng = random.Random(seed)
    docs = [parse_row(r) for off in rng.sample(range(0, SPLIT_ROWS - 100, 100), pages) for r in fetch(off, split="train")]
    by_domain: dict[str, list[Doc]] = {}
    for d in docs:
        by_domain.setdefault(d.domain, []).append(d)
    for ds in by_domain.values():
        rng.shuffle(ds)
    order = []  # round-robin across domains so no one document type dominates
    while any(by_domain.values()):
        for dom in sorted(by_domain):
            if by_domain[dom]:
                order.append(by_domain[dom].pop())

    rows, empty, seen_paras = [], 0, set()
    for d in order:
        for off, para in paragraphs(d.text):
            if para in exclude or para in seen_paras:  # boilerplate repeats across documents
                continue
            seen_paras.add(para)
            end = off + len(para)
            seen, entities = set(), []
            for g in sorted(d.spans, key=lambda g: g.start):
                text = d.text[g.start:g.end]
                if off <= g.start and g.end <= end and text.strip() and (text, LABEL_MAP[g.label]) not in seen:
                    seen.add((text, LABEL_MAP[g.label]))
                    entities.append({"text": text, "type": LABEL_MAP[g.label]})
            if not entities:
                if empty >= empty_share * n:
                    continue
                empty += 1
            sentences = split_sentences(para) or [para]
            r = chat_row(sentences, json.dumps({"entities": entities, "contexts": []}, ensure_ascii=False))
            if _approx_tokens(r) > max_tokens:
                continue
            a = parse(r["messages"][-1]["content"], para, sentences)
            if a.dropped:  # gold text not findable verbatim: skip rather than teach a mismatch
                continue
            r["_meta"] = {"source": "nemotron", "domain": d.domain, "locale": d.locale, "format": d.format,
                          "uid": d.uid, "approx_tokens": _approx_tokens(r)}
            rows.append(r)
            if len(rows) >= n:
                return rows
    return rows


def build_mix(test_sample: Path, n_nemotron: int = 4000, n_synthetic: int = 1000, seed: int = 101, fetch=_fetch_page) -> list[dict]:
    rows, seen = [], set()
    for r in nemotron_rows(n_nemotron, seed, benchmark_paragraphs(test_sample), fetch=fetch) + build(n_synthetic, seed):
        key = r["messages"][3]["content"]
        if key not in seen:  # identical prompts would just over-weight one example
            seen.add(key)
            rows.append(r)
    random.Random(seed).shuffle(rows)
    return rows


def _write(out: Path, rows: list[dict], val_fraction: float) -> dict:
    k = max(1, int(len(rows) * val_fraction))
    out.mkdir(parents=True, exist_ok=True)
    for name, chunk in (("val", rows[:k]), ("train", rows[k:])):
        # Training files carry only `messages`; where each row came from goes to a sidecar
        # manifest (same order), for per-sector stats and per-sector datasets later.
        with (out / f"{name}.jsonl").open("w") as f, (out / f"{name}.manifest.jsonl").open("w") as m:
            for r in chunk:
                f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
                m.write(json.dumps(r.get("_meta", {}), ensure_ascii=False) + "\n")
    types: dict[str, int] = {}
    for r in rows:
        for e in json.loads(r["messages"][-1]["content"])["entities"]:
            types[e["type"]] = types.get(e["type"], 0) + 1
    return {"train": len(rows) - k, "val": k, "dir": str(out),
            "approx_longest_row_tokens": max(_approx_tokens(r) for r in rows),
            "rows_with_contexts": sum(bool(json.loads(r["messages"][-1]["content"])["contexts"]) for r in rows),
            "entities_by_type": dict(sorted(types.items()))}


def export_mix(out: Path, test_sample: Path, n_nemotron: int = 4000, n_synthetic: int = 1000, seed: int = 101,
               val_fraction: float = 0.05) -> dict:
    return _write(out, build_mix(test_sample, n_nemotron, n_synthetic, seed), val_fraction)


def export(out: Path, n: int = 600, seed: int = 101, val_fraction: float = 0.1) -> dict:
    rows = build(n, seed)
    k = max(1, int(len(rows) * val_fraction))
    out.mkdir(parents=True, exist_ok=True)
    for name, chunk in (("val", rows[:k]), ("train", rows[k:])):
        with (out / f"{name}.jsonl").open("w") as f:
            for r in chunk:
                f.write(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n")
    longest = max(sum(len(m["content"]) for m in r["messages"]) for r in rows)
    return {"train": len(rows) - k, "val": k, "dir": str(out), "longest_row_chars": longest,
            "approx_longest_row_tokens": longest // 3}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.trainset")
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--seed", type=int, default=101)
    ap.add_argument("--out", type=Path, default=Path("runs/train"))
    ap.add_argument("--mix", action="store_true", help="Nemotron-PII train paragraphs + synthetic contract rows")
    ap.add_argument("--nemotron", type=int, default=4000)
    ap.add_argument("--synthetic", type=int, default=1000)
    ap.add_argument("--test-sample", type=Path, default=Path("runs/benchmarks/nemotron-test-500-s7.jsonl"),
                    help="benchmark docs whose paragraphs must never appear in training (required with --mix)")
    args = ap.parse_args(argv)
    if args.mix:
        if not args.test_sample.exists():
            ap.error(f"--test-sample {args.test_sample} not found: the leakage guard needs it")
        print(json.dumps(export_mix(args.out, args.test_sample, args.nemotron, args.synthetic, args.seed), indent=2))
    else:
        print(json.dumps(export(args.out, args.n, args.seed), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
