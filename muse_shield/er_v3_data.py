"""er-v3 training data: the er-v2 documents, the v3 families, Nemotron-PII *train* rows and (one variant) half of PUPA.

    .venv/bin/python -m muse_shield.er_v3_data build --out runs/er/v3

Contamination rules (checked here, recorded in manifest.json):
- Nemotron-PII rows come from the train split only. The 500 benchmark docs are from the test split; any train doc
  whose uid or normalised text matches one of them is dropped anyway, and so is any doc sharing a 12-word run with
  them. A further 150 train docs are held out for checkpoint checks and never trained on.
- PUPA has no train split. Only variant C uses it: the eligible prompts are split 50/50 by conversation (stratified by
  category, seed 7); C trains on one half, and every model is scored on the other half only.
- No training text may share a 12-word run with any benchmark or test text: Nemotron test 500, all of PUPA (minus
  C's train half for C), TAB test, and our er test, challenge and ambiguity sets.

All rows use the v3 prompt (resolution.SYSTEM_PROMPT_V3). Nemotron rows have no pronouns, roles, owners or relations,
so they carry the values-only note (variant D drops the note to test whether it matters).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from muse_shield import resolution as R
from muse_shield import resolution_data as D
from muse_shield.benchmarks.nemotron import LABEL_MAP, QUASI

REPO = Path(__file__).resolve().parents[1]
MAIN = Path("/Users/majjir/muse-shield")
NEMO_TRAIN = Path("/Volumes/MajjiR/ai/datasets/nemotron/train.jsonl")
NEMO_TEST = MAIN / "runs/benchmarks/nemotron-test-500-s7.jsonl"
PUPA_DIR = Path("/Volumes/MajjiR/ai/datasets/pupa")
TAB_TEST = Path("/Volumes/MajjiR/ai/datasets/tab/test.parquet")
ER_V1 = REPO / "data/er-v1"
ER_V2_NEW = MAIN / "data/er-v2/new.docs.jsonl"

SUBTYPE = {
    "email": ("CONTACT", "EMAIL"), "phone_number": ("CONTACT", "PHONE"), "fax_number": ("CONTACT", "PHONE"),
    "url": ("CONTACT", "URL"), "user_name": ("CONTACT", "USERNAME"),
    "account_number": ("ID", "BANK_ACCOUNT"), "credit_debit_card": ("ID", "CARD"), "ssn": ("ID", "SSN"), "tax_id": ("ID", "TAX_ID"),
    "customer_id": ("ID", "CUSTOMER_ID"), "employee_id": ("ID", "EMPLOYEE_ID"), "medical_record_number": ("ID", "MEDICAL_RECORD"),
    "ipv4": ("ID", "IP_ADDRESS"), "ipv6": ("ID", "IP_ADDRESS"), "mac_address": ("ID", "DEVICE"), "device_identifier": ("ID", "DEVICE"),
    "vehicle_identifier": ("ID", "VEHICLE"), "license_plate": ("ID", "VEHICLE"), "certificate_license_number": ("ID", "LICENSE"),
    "health_plan_beneficiary_number": ("ID", "POLICY"),
    "date_of_birth": ("DATE", "DOB"), "time": ("DATE", "TIME"), "date_time": ("DATE", "EVENT"), "date": ("DATE", "OTHER"),
    "city": ("LOCATION", "CITY"), "county": ("LOCATION", "OTHER"), "state": ("LOCATION", "STATE"), "country": ("LOCATION", "COUNTRY"),
    "postcode": ("LOCATION", "OTHER"), "coordinate": ("LOCATION", "OTHER"),
    "street_address": ("ADDRESS", "OTHER"),
    "password": ("SECRET", "PASSWORD"), "api_key": ("SECRET", "API_KEY"), "pin": ("SECRET", "PIN"), "cvv": ("SECRET", "PIN"),
    "http_cookie": ("SECRET", "OTHER"),
    "age": ("SENSITIVE_ATTRIBUTE", "AGE"), "gender": ("SENSITIVE_ATTRIBUTE", "GENDER"), "religious_belief": ("SENSITIVE_ATTRIBUTE", "RELIGION"),
    "political_view": ("SENSITIVE_ATTRIBUTE", "POLITICS"), "race_ethnicity": ("SENSITIVE_ATTRIBUTE", "CASTE_ETHNICITY"),
    "sexuality": ("SENSITIVE_ATTRIBUTE", "SEXUALITY"), "blood_type": ("SENSITIVE_ATTRIBUTE", "HEALTH"),
}
NGRAM = 12


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def ngrams(text: str, n: int = NGRAM) -> set[int]:
    w = re.findall(r"\w+", text.lower())
    return {hash(" ".join(w[i:i + n])) for i in range(max(0, len(w) - n + 1))}


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# -- Nemotron span rows -> contract docs ---------------------------------------------------------

def nemotron_doc(row: dict) -> dict | None:
    """One Nemotron train row as a gold contract doc (values only), or None if it can't be grounded cleanly."""
    text, spans = row["text"], sorted(row["spans"], key=lambda s: s["start"])
    if len(text) > 5000:
        return None
    vals = []
    for s in spans:
        lab = s["label"]
        if lab in QUASI or lab not in LABEL_MAP:
            continue
        vals.append([int(s["start"]), int(s["end"]), lab])
    # first + last name next to each other: one PERSON mention
    merged: list[list] = []
    for v in vals:
        if merged and merged[-1][2] in ("first_name", "last_name", "name") and v[2] in ("first_name", "last_name") \
                and text[merged[-1][1]:v[0]] in (" ", " "):
            merged[-1] = [merged[-1][0], v[1], "name"]
        else:
            merged.append(v)
    us = R.units(text)
    ents: dict[tuple, dict] = {}
    persons_full: list[dict] = []
    for s, e, lab in merged:
        if not any(a <= s and e <= b for a, b in us) or not text[s:e].strip():
            return None  # a span across a unit boundary can't be a [unit, text] mention
        surface = text[s:e]
        if lab in ("first_name", "last_name", "name"):
            key = ("PERSON", _norm(surface))
            ent = ents.setdefault(key, {"type": "PERSON", "mentions": []})
            if " " in surface.strip() and ent not in persons_full:
                persons_full.append(ent)
        else:
            t, sub = SUBTYPE.get(lab, (LABEL_MAP[lab], None))
            ent = ents.setdefault((t, sub, _norm(surface)), {"type": t, "subtype": sub, "mentions": []})
        ent["mentions"].append((s, e))
    # a lone first or last name that belongs to exactly one full name joins that person
    for key in list(ents):
        if key[0] != "PERSON" or " " in key[1]:
            continue
        owners = [p for p in persons_full if any(key[1] in _norm(text[a:b]).split() for a, b in p["mentions"])]
        if len(owners) == 1 and ents[key] is not owners[0]:
            owners[0]["mentions"] += ents.pop(key)["mentions"]
    if not ents:
        return None
    order = sorted(ents.values(), key=lambda x: min(m[0] for m in x["mentions"]))
    counts, out = defaultdict(int), []
    for x in order:
        counts[x["type"]] += 1
        item = {"id": f"{x['type']}_{counts[x['type']]}", "type": x["type"], "mentions": sorted(x["mentions"])}
        if x.get("subtype"):
            item["subtype"] = x["subtype"]
        out.append(item)
    return {"uid": f"nemo-{row['uid']}", "family": "nemotron", "text": text, "entities": out, "relations": []}


def nemotron_docs(n: int, holdout: int, seed: int, banned: set[int]) -> tuple[list[dict], list[dict], dict]:
    test = _load(NEMO_TEST)
    test_uids, test_texts = {d["uid"] for d in test}, {_norm(d["text"]) for d in test}
    rows = _load(NEMO_TRAIN)
    random.Random(seed).shuffle(rows)
    kept, stats = [], defaultdict(int)
    for r in rows:
        if len(kept) >= n + holdout:
            break
        if r["uid"] in test_uids or _norm(r["text"]) in test_texts:
            stats["same as a test doc"] += 1
            continue
        if ngrams(r["text"]) & banned:
            stats["shares a 12-word run with a benchmark"] += 1
            continue
        d = nemotron_doc(r)
        if d is None:
            stats["not groundable"] += 1
            continue
        kept.append(d)
    return kept[holdout:], kept[:holdout], dict(stats)


# -- v3 relabel of the er-v2 documents -------------------------------------------------------------

_TIME = re.compile(r"\b\d{1,2}:\d{2}(?:\s?(?:AM|PM|am|pm|a\.m\.|p\.m\.))?|\b\d{1,2}\s?(?:am|pm|AM|PM|a\.m\.|p\.m\.)(?!\w)")
_PLACES = sorted(set(D.WORLD_CITIES + D.STATES + D.COUNTRIES + [c for c, _ in D.IN_CITIES] + [c for c, *_ in D.US_PLACES]),
                 key=len, reverse=True)


def relabel_v3(doc: dict) -> dict:
    """er-v2 gold under the v3 policy: places and times written outside any tagged value become entities."""
    text = doc["text"]
    taken = [False] * len(text)
    for e in doc["entities"]:
        for s, t in e["mentions"]:
            for i in range(s, t):
                taken[i] = True
    new: dict[tuple, dict] = {}
    us = R.units(text)

    def grab(kind, sub, s, t):
        if any(taken[s:t]) or not any(a <= s and t <= b for a, b in us):
            return
        x = new.setdefault((kind, sub, text[s:t].lower()), {"type": kind, "subtype": sub, "mentions": []})
        x["mentions"].append([s, t])
        for i in range(s, t):
            taken[i] = True
    for g in _PLACES:
        for m in re.finditer(rf"(?<![\w]){re.escape(g)}(?![\w])", text):
            grab("LOCATION", "COUNTRY" if g in D.COUNTRIES else ("STATE" if g in D.STATES else "CITY"), m.start(), m.end())
    for m in _TIME.finditer(text):
        grab("DATE", "TIME", m.start(), m.end())
    if not new:
        return doc
    ents = [dict(e) for e in doc["entities"]] + list(new.values())
    ents.sort(key=lambda e: min(s for s, _ in e["mentions"]))
    # renumber, keeping AMOUNT ids by role; owners and relations follow the old ids
    counts, ids = defaultdict(int), {}
    for e in ents:
        base = e["id"].rsplit("_", 1)[0] if e.get("id") and e["type"] == "AMOUNT" else e["type"]
        counts[base] += 1
        ids[id(e)] = f"{base}_{counts[base]}"
    old2new = {e["id"]: ids[id(e)] for e in ents if e.get("id")}
    out = []
    for e in ents:
        item = {**e, "id": ids[id(e)]}
        if item.get("owner") and item["owner"] != R.UNKNOWN:
            item["owner"] = old2new.get(item["owner"], R.UNKNOWN)
        out.append(item)
    rels = [[old2new[a], r, old2new[b]] for a, r, b in doc.get("relations", []) if a in old2new and b in old2new]
    return {**doc, "entities": out, "relations": rels, "v3_added": sum(len(x["mentions"]) for x in new.values())}


# -- PUPA split ------------------------------------------------------------------------------------

def pupa_rows() -> list[dict]:
    """The eligible PUPA prompts, exactly as scripts/pupa_eval.py filters them (before its sampling)."""
    csv.field_size_limit(10**8)
    rows = []
    for f in ("PUPA_New.csv", "PUPA_TNB.csv"):
        with open(PUPA_DIR / f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                q, units = r.get("user_query") or "", r.get("pii_units") or ""
                if not q or not units or len(q) > 3000 or sum(c.isascii() for c in q) / max(1, len(q)) < 0.97:
                    continue
                real = [u.strip() for u in units.split("||") if u.strip() and "presidio_anonymized" not in u.lower()]
                real = [u for u in real if u.lower() in q.lower()]
                if real:
                    rows.append({"id": f"{f.split('_')[1].split('.')[0].lower()}-{r['conversation_hash']}", "hash": r["conversation_hash"],
                                 "category": r["predicted_category"], "query": q, "units": real})
    return rows


def pupa_split(seed: int = 7) -> tuple[list[dict], list[dict]]:
    """50/50 by conversation, stratified by category. A conversation never lands on both sides."""
    by_hash: dict[str, list[dict]] = defaultdict(list)
    for r in pupa_rows():
        by_hash[r["hash"]].append(r)  # the same conversation can be in both CSVs, under different categories
    by_cat: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for h, rs in by_hash.items():
        by_cat[rs[0]["category"]][h] = rs
    train, test = [], []
    rng = random.Random(seed)
    for cat in sorted(by_cat):
        hashes = sorted(by_cat[cat])
        rng.shuffle(hashes)
        half = len(hashes) // 2
        for i, h in enumerate(hashes):
            (train if i < half else test).extend(by_cat[cat][h])
    return train, test


PUPA_TYPE_PROMPT = """Each item below is a private detail found in a chatbot prompt. Give each one a type from: PERSON, ORG,
LOCATION, ADDRESS, CONTACT, ID, DATE, AMOUNT, PROJECT, SECRET, SENSITIVE_ATTRIBUTE.
(ORG: companies, schools, banks, brands, apps, agencies. LOCATION: cities, states, countries, places. CONTACT: emails,
phones, websites, usernames. PROJECT: product or project names. SENSITIVE_ATTRIBUTE: health, religion, gender, politics.)

Prompt (for context):
{query}

Items:
{items}

Return JSON: {{"types": ["<TYPE>", ...]}} with one type per item, in order."""


def pupa_docs(train_rows: list[dict], workers: int = 32) -> list[dict]:
    """Gold docs for PUPA's train half: every occurrence of each unit is one entity; DeepSeek Flash only types them."""
    from concurrent.futures import ThreadPoolExecutor

    from muse_shield.backends import DeepSeekBackend
    from muse_shield.analysis import _loads

    ds = DeepSeekBackend("deepseek-flash", max_tokens=600, extra={"thinking": {"type": "disabled"}})

    def one(r):
        msg = [{"role": "user", "content": PUPA_TYPE_PROMPT.format(query=r["query"][:3000],
                                                                  items="\n".join(f"{i + 1}. {u}" for i, u in enumerate(r["units"])))}]
        try:
            raw, _ = ds._call(msg)
            types = [str(t).upper() for t in _loads(raw).get("types", [])]
        except Exception:  # noqa: BLE001 - a row we can't type is skipped
            return None
        if len(types) != len(r["units"]) or any(t not in R.ENTITY_TYPES for t in types):
            return None
        text, us = r["query"], R.units(r["query"])
        taken = [False] * len(text)
        ents, counts = [], defaultdict(int)
        for u, t in sorted(zip(r["units"], types), key=lambda x: -len(x[0])):
            ms = []
            for m in re.finditer(re.escape(u), text, re.IGNORECASE):
                s, e = m.start(), m.end()
                if any(taken[s:e]) or not any(a <= s and e <= b for a, b in us):
                    continue
                ms.append((s, e))
                for i in range(s, e):
                    taken[i] = True
            if ms:
                ents.append({"type": t, "mentions": ms})
        if not ents:
            return None
        ents.sort(key=lambda e: e["mentions"][0][0])
        for e in ents:
            counts[e["type"]] += 1
            e["id"] = f"{e['type']}_{counts[e['type']]}"
        return {"uid": f"pupa-{r['id']}", "family": "pupa", "text": text, "entities": ents, "relations": []}

    with ThreadPoolExecutor(workers) as pool:
        return [d for d in pool.map(one, train_rows) if d]


# -- assembly --------------------------------------------------------------------------------------

def row(doc: dict, values_only: bool = False) -> dict:
    return {"messages": R.messages(doc["text"], example=False, version="v3", values_only=values_only) +
            [{"role": "assistant", "content": R.target_json(doc["text"], doc)}]}


def banned_ngrams(pupa_exempt: set[str] = frozenset()) -> tuple[set[int], dict]:
    sizes, banned = {}, set()
    for name, texts in (("nemotron-test-500", [d["text"] for d in _load(NEMO_TEST)]),
                        ("pupa", [r["query"] for r in pupa_rows() if r["id"] not in pupa_exempt]),
                        ("er-test", [d["text"] for d in _load(ER_V1 / "test.docs.jsonl")]),
                        ("er-challenge", [d["text"] for d in _load(ER_V1 / "challenge.docs.jsonl")]),
                        ("er-ambiguity", [d["text"] for d in _load(ER_V1 / "ambiguity.docs.jsonl")])):
        g = set().union(*(ngrams(t) for t in texts)) if texts else set()
        sizes[name] = len(texts)
        banned |= g
    try:
        import pandas as pd

        tab = pd.read_parquet(TAB_TEST).drop_duplicates("doc_id")
        banned |= set().union(*(ngrams(t[:6000]) for t in tab.text))
        sizes["tab-test"] = len(tab)
    except Exception:  # noqa: BLE001 - no pandas in this venv: TAB (legal judgments) can't overlap our sources anyway
        sizes["tab-test"] = "skipped (pandas unavailable)"
    return banned, sizes


def build(out: Path, gen3: Path, n_nemo: int, holdout: int, v3_val: int, seed: int = 13) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    pupa_train, pupa_test = pupa_split()
    banned, sizes = banned_ngrams()
    manifest = {"benchmark_texts_banned": sizes, "ngram": NGRAM, "dropped_for_overlap": {}}

    def clean(docs: list[dict], name: str, ban: set[int] = banned) -> list[dict]:
        ok = [d for d in docs if not (ngrams(d["text"]) & ban)]
        manifest["dropped_for_overlap"][name] = len(docs) - len(ok)
        return ok

    v2 = clean([relabel_v3(d) for d in _load(ER_V1 / "train.docs.jsonl") +
                [d for d in _load(ER_V2_NEW) if d["family"] not in D.CHALLENGE_FAMILIES]], "er-v2")
    v3 = [d for d in _load(gen3 / "docs.jsonl") if d["entities"] or d["family"] == "generic"]
    rng.shuffle(v3)
    v3_val_docs, v3 = v3[:v3_val], clean(v3[v3_val:], "v3-families")
    nemo, nemo_hold, nemo_stats = nemotron_docs(n_nemo, holdout, seed, banned)
    manifest["nemotron"] = {"train": len(nemo), "holdout": len(nemo_hold), "skipped": nemo_stats}
    er_val = _load(ER_V1 / "val.docs.jsonl")

    # held-out sets for checkpoint checks (never trained on)
    for name, docs in (("heldout-er-val", er_val), ("heldout-v3-val", v3_val_docs), ("heldout-nemotron-train", nemo_hold)):
        (out / f"{name}.docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs))
    (out / "pupa-test.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pupa_test))
    (out / "pupa-train-ids.json").write_text(json.dumps(sorted(r["id"] for r in pupa_train)))

    pupa = []
    if pupa_train:
        ban_c, _ = banned_ngrams(pupa_exempt={r["id"] for r in pupa_train})
        pupa = clean(pupa_docs(pupa_train), "pupa-train-half", ban_c)
        test_g = set().union(*(ngrams(r["query"]) for r in pupa_test))
        assert not any(ngrams(d["text"]) & test_g for d in pupa), "PUPA train half overlaps the test half"
    manifest["pupa"] = {"train_prompts": len(pupa_train), "train_docs": len(pupa), "test_prompts": len(pupa_test),
                        "test_units": sum(len(r["units"]) for r in pupa_test)}

    variants = {
        "A": [row(d) for d in v2 + v3] + [row(d, values_only=True) for d in nemo],
        "B": [row(d) for d in v2 + v3],
        "C": [row(d) for d in v2 + v3 + pupa + pupa] + [row(d, values_only=True) for d in nemo],
        "D": [row(d) for d in v2 + v3 + nemo],
    }
    val_rows = [row(d) for d in er_val + v3_val_docs[:40]]
    for k, rows in variants.items():
        random.Random(seed + ord(k)).shuffle(rows)
        d = out / k
        d.mkdir(exist_ok=True)
        (d / "train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        (d / "val.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in val_rows))
    manifest["rows"] = {k: len(v) for k, v in variants.items()}
    manifest["sources"] = {"er-v2 (v3 relabel)": len(v2), "v3 families": len(v3), "v3 val held out": len(v3_val_docs),
                           "v3 relabel added mentions": sum(d.get("v3_added", 0) for d in v2)}
    manifest["families_v3"] = {f: sum(d["family"] == f for d in v3) for f in sorted({d["family"] for d in v3})}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.er_v3_data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, default=Path("runs/er/v3"))
    b.add_argument("--gen3", type=Path, default=Path("runs/er/gen3"))
    b.add_argument("--nemotron", type=int, default=4000)
    b.add_argument("--holdout", type=int, default=150)
    b.add_argument("--v3-val", type=int, default=80)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.out, a.gen3, a.nemotron, a.holdout, a.v3_val), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
