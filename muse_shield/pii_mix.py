"""Stage-1 PII training mix from public datasets plus our planted-value sector documents.

    .venv/bin/python -m muse_shield.pii_mix --out runs/train/pii-v1

Sources (licence; how labelled):
- nvidia/Nemotron-PII train (CC-BY-4.0; by construction)
- gretelai/synthetic_pii_finance_multilingual, English (Apache-2.0; LLM + model check + LLM judge)
- gretelai/gretel-pii-masking-en-v1 (Apache-2.0; values only, located in the text here)
- data/synth-v2/train (ours; code-planted values, Spark double-labelled)
(piimb/privy is excluded: it marks emails and URLs as "O", which would teach leaving them unmasked.)

Every source goes through one labelling policy: our 11 types; full names as one span (first + last
merged); no job titles or employment/education/language; specific dates and times only; the longest
span wins on overlap. A paragraph is skipped when a label crosses its boundary, and so is a Gretel-en
document when a listed value can't be found in its text. Rows use the stage-1 "pii" prompt
(entities only). Benchmark paragraphs and every source's test split are excluded from training.
Raw parquet is converted to JSONL on the SSD (DATASETS, default /Volumes/MajjiR/ai/datasets).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
from pathlib import Path

from .analysis import split_sentences
from .backends import task_messages
from .benchmarks.nemotron import LABEL_MAP, QUASI, paragraphs
from .trainset import para_key, specific_date

DATASETS = Path(os.environ.get("DATASETS", "/Volumes/MajjiR/ai/datasets"))
BENCH = Path(__file__).resolve().parents[3] / "runs" / "benchmarks" / "nemotron-test-500-s7.jsonl"

GRETEL_MAP = {
    **dict.fromkeys(["name", "first_name", "last_name"], "PERSON"),
    **dict.fromkeys(["company", "company_name"], "ORG"),
    **dict.fromkeys(["street_address", "address"], "ADDRESS"),
    **dict.fromkeys(["city", "country", "state", "postcode", "coordinate", "local_latlng"], "LOCATION"),
    **dict.fromkeys(["date", "date_of_birth", "date_time", "time"], "DATE"),
    **dict.fromkeys(["email", "phone_number", "user_name", "url"], "CONTACT"),
    **dict.fromkeys(["customer_id", "employee_id", "passport_number", "driver_license_number", "ssn", "iban", "bban",
                     "bank_routing_number", "swift_bic_code", "swift_bic", "credit_card_number", "ipv4", "ipv6",
                     "medical_record_number", "license_plate", "device_identifier", "unique_identifier",
                     "biometric_identifier", "account_number", "certificate_license_number", "vehicle_identifier",
                     "national_id", "health_plan_beneficiary_number", "tax_id"], "ID"),
    **dict.fromkeys(["account_pin", "credit_card_security_code", "cvv", "pin", "api_key", "password"], "SECRET"),
}
_MONTH_DATE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)? (?:January|February|March|April|May|June|July|August|September|October|"
                         r"November|December) \d{4}\b")
# Gretel leaves many specific dates unlabelled (ISO dates, timestamps, "March 15, 2023"); our policy labels
# every specific date, so these are completed in Gretel rows (audit 2026-11-04: 809 rows affected).
_DATE_FORMS = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)?\b"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}(?:st|nd|rd|th)?, \d{4}\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)? (?:January|February|March|April|May|June|July|August|September|October|November|December),? \d{4}\b")
MAX_CHARS, MIN_CHARS = 2500, 20


def complete_dates(text: str, spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    added = [(m.start(), m.end(), "DATE") for m in _DATE_FORMS.finditer(text)
             if not any(m.start() < e and s < m.end() for s, e, _ in spans)]
    return spans + added


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def normalise(text: str, spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Policy for one document: drop out-of-policy dates, longest span on overlap, merge 'First Last'."""
    spans = [s for s in spans if s[2] != "DATE" or specific_date(text[s[0]:s[1]])]
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    kept: list[tuple[int, int, str]] = []
    for s in spans:
        if kept and s[0] < kept[-1][1]:  # overlap: keep the longer one
            if s[1] - s[0] > kept[-1][1] - kept[-1][0]:
                kept[-1] = s
            continue
        kept.append(s)
    merged: list[tuple[int, int, str]] = []
    for s in kept:
        if merged and s[2] == "PERSON" == merged[-1][2] and text[merged[-1][1]:s[0]] == " ":
            merged[-1] = (merged[-1][0], s[1], "PERSON")
        else:
            merged.append(s)
    return merged


def doc_paragraph_rows(doc: dict, spans: list[tuple[int, int, str]], source: str, per_doc: int, rng: random.Random,
                       exclude: set[str]) -> list[dict]:
    text = doc["text"]
    paras = [(o, p) for o, p in paragraphs(text) if MIN_CHARS <= len(p) <= MAX_CHARS and para_key(p) not in exclude]
    rng.shuffle(paras)
    out = []
    for off, para in paras:
        end = off + len(para)
        if any(s[0] < end and s[1] > off and not (s[0] >= off and s[1] <= end) for s in spans):
            continue  # a label crosses the paragraph boundary
        inside = [s for s in spans if s[0] >= off and s[1] <= end]
        if not inside and len(para) < 40:
            continue  # headings like "**Guest Information:**" teach nothing
        ents, seen = [], set()
        for s, e, t in inside:
            k = (text[s:e], t)
            if k[0].strip() and k not in seen:
                seen.add(k)
                ents.append({"text": k[0], "type": t})
        out.append(make_row(para, ents, source, doc.get("domain", ""), doc["uid"]))
        if len(out) >= per_doc:
            break
    return out


def make_row(paragraph: str, entities: list[dict], source: str, domain: str, uid: str) -> dict:
    sentences = split_sentences(paragraph) or [paragraph]
    msgs = task_messages("pii", sentences) + [{"role": "assistant", "content": json.dumps({"entities": entities}, ensure_ascii=False)}]
    return {"messages": msgs, "_meta": {"source": source, "domain": domain, "doc": uid, "para_key": para_key(paragraph),
                                        "n_entities": len(entities)}}


def nemotron_spans(doc: dict) -> list[tuple[int, int, str]]:
    return normalise(doc["text"], [(s["start"], s["end"], LABEL_MAP[s["label"]]) for s in doc["spans"]
                                   if s["label"] in LABEL_MAP and s["label"] not in QUASI])


def gretel_fin_spans(doc: dict) -> list[tuple[int, int, str]]:
    spans = [(s["start"], s["end"], GRETEL_MAP[s["label"]]) for s in doc["spans"] if s["label"] in GRETEL_MAP]
    return normalise(doc["text"], complete_dates(doc["text"], spans))


def gretel_en_spans(doc: dict) -> list[tuple[int, int, str]] | None:
    """Values without offsets: label every occurrence. None if any listed value isn't in the text."""
    spans = []
    for v in doc["values"]:
        etype = next((GRETEL_MAP[t] for t in v["types"] if t in GRETEL_MAP), None)
        hits = [m.span() for m in re.finditer(re.escape(v["value"]), doc["text"])] if v["value"].strip() else []
        if not hits:
            return None
        if etype:
            spans += [(a, b, etype) for a, b in hits]
    return normalise(doc["text"], complete_dates(doc["text"], spans))


def sector_rows(path: Path, rng: random.Random, n: int) -> list[dict]:
    """Our planted-value sector rows, entities only; every specific '12 March 2027' date labelled (policy)."""
    rows = load_jsonl(path / "rows.jsonl")
    metas = load_jsonl(path / "rows.manifest.jsonl")
    out = []
    for r, m in zip(rows, metas):
        para = " ".join(re.sub(r"^\[\d+\] ", "", s) for s in re.split(r" (?=\[\d+\] )", r["messages"][3]["content"].split("\n", 1)[1]))
        gold = json.loads(r["messages"][-1]["content"])
        ents = [{k: e[k] for k in ("text", "type", "role") if e.get(k)} for e in gold["entities"]]
        have = {e["text"] for e in ents}
        ents += [{"text": d, "type": "DATE"} for d in dict.fromkeys(_MONTH_DATE.findall(para)) if d not in have]
        out.append(make_row(para, ents, "synthetic-spark", m.get("domain", ""), m.get("doc_id", "")))
    rng.shuffle(out)
    return out[:n]


def take(rows: list[dict], n: int, max_empty: float, rng: random.Random) -> list[dict]:
    """n rows with at most max_empty share of 'no PII' paragraphs (hard negatives)."""
    rng.shuffle(rows)
    pos = [r for r in rows if r["_meta"]["n_entities"]]
    neg = [r for r in rows if not r["_meta"]["n_entities"]]
    k_neg = min(len(neg), int(n * max_empty))
    return pos[: n - k_neg] + neg[:k_neg]


def build(out: Path, seed: int, quotas: dict[str, int], per_doc: int, max_empty: float, val_per_source: int) -> dict:
    rng = random.Random(seed)
    bench = {para_key(p) for d in load_jsonl(BENCH) for _, p in paragraphs(d["text"])} if BENCH.exists() else set()
    exclude = set(bench)
    for test in (DATASETS / "gretel-finance/test.en.jsonl", DATASETS / "gretel-en/test.jsonl", DATASETS / "gretel-en/validation.jsonl"):
        exclude |= {para_key(p) for d in load_jsonl(test) for _, p in paragraphs(d["text"])}
    stats, train, val = {"excluded_paragraph_keys": len(exclude)}, [], []
    seen_text: set[str] = set()

    def source_rows(name: str, docs: list[dict], span_fn) -> None:
        rng.shuffle(docs)
        n_val_docs = max(30, val_per_source // 2)
        rows_val, rows_train, skipped = [], [], 0
        for i, d in enumerate(docs):
            if d["text"] in seen_text:
                continue
            seen_text.add(d["text"])
            spans = span_fn(d)
            if spans is None:
                skipped += 1
                continue
            rows = doc_paragraph_rows(d, spans, name, per_doc if i >= n_val_docs else 2, rng, exclude)
            (rows_val if i < n_val_docs else rows_train).extend(rows)
            if len(rows_train) >= quotas[name] * 3:
                break
        tr = take(rows_train, quotas[name], max_empty, rng)
        va = take(rows_val, val_per_source, max_empty, rng)
        train.extend(tr), val.extend(va)
        stats[name] = {"docs_seen": i + 1, "docs_skipped_unlocatable": skipped, "train": len(tr), "val": len(va),
                       "train_empty": sum(not r["_meta"]["n_entities"] for r in tr)}

    source_rows("nemotron", load_jsonl(DATASETS / "nemotron/train.jsonl"), nemotron_spans)
    source_rows("gretel-finance", load_jsonl(DATASETS / "gretel-finance/train.en.jsonl"), gretel_fin_spans)
    source_rows("gretel-en", load_jsonl(DATASETS / "gretel-en/train.jsonl"), gretel_en_spans)
    sec = sector_rows(Path(__file__).resolve().parents[1] / "data/synth-v2/train", rng, quotas["synthetic-spark"])
    train.extend(sec)
    stats["synthetic-spark"] = {"train": len(sec)}
    rng.shuffle(train)
    leaks = sum(r["_meta"]["para_key"] in bench for r in train)
    assert leaks == 0, f"{leaks} benchmark paragraphs in training"
    types = collections.Counter(e["type"] for r in train for e in json.loads(r["messages"][-1]["content"])["entities"])
    stats.update(total_train=len(train), total_val=len(val), entity_types=dict(types.most_common()), benchmark_leaks=leaks, seed=seed)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("val", val)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps({"messages": r["messages"]}, ensure_ascii=False) + "\n" for r in rows))
        (out / f"{name}.manifest.jsonl").write_text("".join(json.dumps(r["_meta"], ensure_ascii=False) + "\n" for r in rows))
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.pii_mix")
    ap.add_argument("--out", type=Path, default=Path("runs/train/pii-v1"))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--nemotron", type=int, default=6000)
    ap.add_argument("--gretel-finance", type=int, default=3500)
    ap.add_argument("--gretel-en", type=int, default=3500)
    ap.add_argument("--sector", type=int, default=1500)
    ap.add_argument("--per-doc", type=int, default=3, help="max paragraphs taken from one document")
    ap.add_argument("--max-empty", type=float, default=0.12, help="max share of no-PII paragraphs per source")
    ap.add_argument("--val-per-source", type=int, default=100)
    a = ap.parse_args(argv)
    quotas = {"nemotron": a.nemotron, "gretel-finance": a.gretel_finance, "gretel-en": a.gretel_en, "synthetic-spark": a.sector}
    print(json.dumps(build(a.out, a.seed, quotas, a.per_doc, a.max_empty, a.val_per_source), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def export_eval(out: Path, seed: int = 7, n_fin: int = 300, n_en: int = 500) -> dict:
    """Held-out PII test sets in the benchmark span format (labels are our type names, same policy as training).
    Gretel's gold misses some PII (see gap_filter), so precision there is understated; leak and recall are fair."""
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for name, path, n, fn in (("gretel-finance-test", DATASETS / "gretel-finance/test.en.jsonl", n_fin, gretel_fin_spans),
                              ("gretel-en-test", DATASETS / "gretel-en/test.jsonl", n_en, gretel_en_spans)):
        docs = load_jsonl(path)
        rng.shuffle(docs)
        rows = []
        for d in docs:
            spans = fn(d)
            if spans is None or not spans:
                continue
            rows.append({"uid": d["uid"], "text": d["text"], "domain": d.get("domain", ""), "locale": "", "format": "",
                         "spans": [{"start": s, "end": e, "text": d["text"][s:e], "label": t} for s, e, t in spans]})
            if len(rows) >= n:
                break
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        stats[name] = {"docs": len(rows), "spans": sum(len(r["spans"]) for r in rows)}
    return stats
