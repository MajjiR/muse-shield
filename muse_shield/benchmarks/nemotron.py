"""nvidia/Nemotron-PII (CC BY 4.0): sampling, label mapping and span scoring.

Every gold span is PII that must not reach the cloud model, so the headline
number is the **leak rate**: the share of gold PII characters left unmasked.
Spans are matched by character overlap, not exact boundaries, because what
matters for privacy is whether the text got covered.
"""

from __future__ import annotations

import ast
import json
import random
import re
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..analysis import Analysis

DATASET = "nvidia/Nemotron-PII"
ROWS_API = "https://datasets-server.huggingface.co/rows?dataset={ds}&config=default&split={split}&offset={off}&length={n}"
SPLIT_ROWS = 100_000

LABEL_MAP = {
    **dict.fromkeys(["first_name", "last_name"], "PERSON"),
    "company_name": "ORG",
    "street_address": "ADDRESS",
    **dict.fromkeys(["city", "county", "state", "country", "postcode", "coordinate"], "LOCATION"),
    **dict.fromkeys(["date", "date_of_birth", "date_time", "time"], "DATE"),
    **dict.fromkeys(["email", "phone_number", "fax_number", "url", "user_name"], "CONTACT"),
    **dict.fromkeys([
        "account_number", "bank_routing_number", "biometric_identifier", "certificate_license_number",
        "credit_debit_card", "customer_id", "device_identifier", "employee_id", "health_plan_beneficiary_number",
        "ipv4", "ipv6", "license_plate", "mac_address", "medical_record_number", "national_id", "ssn",
        "swift_bic", "tax_id", "unique_id", "vehicle_identifier",
    ], "ID"),
    **dict.fromkeys(["api_key", "cvv", "http_cookie", "password", "pin"], "SECRET"),
    **dict.fromkeys([
        "age", "blood_type", "education_level", "employment_status", "gender", "language", "occupation",
        "political_view", "race_ethnicity", "religious_belief", "sexuality",
    ], "SENSITIVE_ATTRIBUTE"),
}
# Weak quasi-identifiers: scored, but reported apart so they don't swing the core leak rate.
QUASI = {"occupation", "employment_status", "education_level", "language"}


@dataclass
class Gold:
    start: int
    end: int
    text: str
    label: str

    @property
    def type(self) -> str:
        return LABEL_MAP.get(self.label, "OTHER")


@dataclass
class Doc:
    uid: str
    text: str
    spans: list[Gold]
    domain: str = ""
    locale: str = ""
    format: str = ""

    def to_dict(self) -> dict:
        return {"uid": self.uid, "text": self.text, "domain": self.domain, "locale": self.locale, "format": self.format,
                "spans": [g.__dict__ for g in self.spans]}

    @classmethod
    def from_dict(cls, d: dict) -> "Doc":
        return cls(d["uid"], d["text"], [Gold(**g) for g in d["spans"]], d.get("domain", ""), d.get("locale", ""), d.get("format", ""))


def parse_row(row: dict) -> Doc:
    spans = row["spans"]
    if isinstance(spans, str):
        spans = ast.literal_eval(spans)
    gold = [Gold(int(s["start"]), int(s["end"]), s["text"], s["label"]) for s in spans]
    return Doc(row["uid"], row["text"], gold, row.get("domain", ""), row.get("locale", ""), row.get("document_format", ""))


def _fetch_page(offset: int, n: int = 100, split: str = "test", tries: int = 5) -> list[dict]:
    url = ROWS_API.format(ds=DATASET, split=split, off=offset, n=n)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return [x["row"] for x in json.load(r)["rows"]]
        except OSError:  # HTTPError / URLError / timeouts from the public rows API
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
    return []


def sample(n: int = 500, seed: int = 7, pages: int = 30, fetch=_fetch_page) -> list[Doc]:
    """Stratified by (locale, domain, format): random pages, then round-robin across strata."""
    rng = random.Random(seed)
    pool = [parse_row(r) for off in rng.sample(range(0, SPLIT_ROWS - 100, 100), pages) for r in fetch(off)]
    strata: dict[tuple, list[Doc]] = defaultdict(list)
    for d in pool:
        strata[(d.locale, d.domain, d.format)].append(d)
    for docs in strata.values():
        rng.shuffle(docs)
    keys = sorted(strata)
    rng.shuffle(keys)
    picked: list[Doc] = []
    while len(picked) < n and any(strata.values()):
        for k in keys:
            if strata[k] and len(picked) < n:
                picked.append(strata[k].pop())
    return picked


def load_or_sample(cache: Path, n: int = 500, seed: int = 7, fetch=_fetch_page) -> list[Doc]:
    if cache.exists():
        docs = [Doc.from_dict(json.loads(l)) for l in cache.read_text().splitlines() if l.strip()]
        if len(docs) >= n:
            return docs[:n]
    docs = sample(n, seed, fetch=fetch)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("".join(json.dumps(d.to_dict(), ensure_ascii=False) + "\n" for d in docs))
    return docs


_PARA = re.compile(r"(?:[^\n]|\n(?![ \t]*\n))+")


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Split on blank lines, keeping each paragraph's offset in the document."""
    out = []
    for m in _PARA.finditer(text):
        chunk = m.group(0)
        lead = len(chunk) - len(chunk.lstrip())
        body = chunk.strip()
        if body:
            out.append((m.start() + lead, body))
    return out


@dataclass
class Pred:
    start: int
    end: int
    text: str
    type: str


def predictions(doc: Doc, analyses: list[tuple[int, Analysis]]) -> list[Pred]:
    return [Pred(off + s.start, off + s.end, s.text, s.type) for off, a in analyses for s in a.entities]


@dataclass
class DocScore:
    gold_chars: int = 0
    leaked_chars: int = 0
    core_gold_chars: int = 0
    core_leaked_chars: int = 0
    gold_found: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))  # label -> [found, total]
    pred_total: int = 0
    pred_on_gold: int = 0
    type_ok: int = 0
    type_checked: int = 0


def score(doc: Doc, preds: list[Pred]) -> DocScore:
    s = DocScore()
    masked = set()
    for p in preds:
        masked.update(range(p.start, p.end))
    for g in doc.spans:
        chars = set(range(g.start, g.end))
        covered = len(chars & masked)
        s.gold_chars += len(chars)
        s.leaked_chars += len(chars) - covered
        if g.label not in QUASI:
            s.core_gold_chars += len(chars)
            s.core_leaked_chars += len(chars) - covered
        found = covered * 2 >= len(chars)  # at least half the span masked
        s.gold_found[g.label][0] += found
        s.gold_found[g.label][1] += 1
    for p in preds:
        s.pred_total += 1
        hits = [g for g in doc.spans if g.start < p.end and p.start < g.end]
        if hits:
            s.pred_on_gold += 1
            s.type_checked += 1
            s.type_ok += any(g.type == p.type for g in hits)
    return s
