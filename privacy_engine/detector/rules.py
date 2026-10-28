"""Deterministic detectors: regexes, checksums and small lexicons.

These run on every request and are the safety net when the local LLM is
unavailable or misses a structured identifier.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..entities import ContextSignal, Entity, EntityType

FIRST_NAMES = frozenset(
    """
    aaron adam aisha alex alice amanda amir ana andrea andrew angela anil anna anthony arjun ben
    benjamin beth brian carlos carol catherine charles chen chris christina claire daniel david
    deepak diana divya elena elizabeth emily emma eric ethan fatima gabriel grace hannah harshal
    hassan helen henry isabella jack jacob james jane jason jennifer jessica john jose joseph
    julia karen kevin kumar laura leo li liam linda lisa lucas maria mark mary matthew mei
    michael michelle mohammed nancy natalie nathan nikhil noah olivia omar patricia paul peter
    priya rachel rahul raj rebecca richard robert rohan ryan sam samantha sanjay sara sarah
    sophia steven susan thomas tom vikram wei william yuki zoe
    """.split()
)

HONORIFICS = r"(?:Mr|Mrs|Ms|Mx|Dr|Prof|Sir|Madam)\.?"
CAP = r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?"

ORG_SUFFIX = (
    r"(?:Inc|Incorporated|Corp|Corporation|LLC|LLP|Ltd|Limited|PLC|GmbH|AG|SA|Co"
    r"|Capital|Partners|Ventures|Holdings|Bank|Group|Technologies|Labs|Systems|Fund)"
)

# Well-known public companies: fine to mention in public context, but in a
# confidential context ("we are acquiring Meta's ...") they become deal intel.
PUBLIC_ORGS = frozenset(
    """
    meta facebook instagram whatsapp google alphabet apple microsoft amazon nvidia openai
    anthropic tesla netflix oracle ibm intel amd salesforce uber airbnb stripe
    """.split()
)

CONFIDENTIAL_CUES = {
    "acquisition": r"\bacqui(?:re|res|ring|sition)\b",
    "merger": r"\bmerg(?:e|er|ing)\b",
    "term sheet": r"\bterm[- ]sheet\b",
    "NDA / confidential marking": r"\b(?:NDA|confidential|internal only|do not share|under embargo|privileged)\b",
    "unannounced plans": r"\b(?:unannounced|not yet public|pre-announcement|stealth)\b",
    "deal valuation": r"\b(?:valuation|pre-money|post-money|offer price|buyout)\b",
    "financial results": r"\b(?:revenue|ebitda|burn rate|runway|earnings) (?:is|was|of|for|will)\b",
    "layoffs / reorg": r"\b(?:layoffs?|reduction in force|RIF|reorg)\b",
    "legal matter": r"\b(?:lawsuit|litigation|settlement|subpoena)\b",
}

MULTIPLIER = r"(?:k|K|m|M|mm|MM|bn|b|B|t|T|thousand|million|billion|trillion)"

_PATTERNS: list[tuple[EntityType, re.Pattern[str]]] = [
    (EntityType.EMAIL, re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        EntityType.API_KEY,
        re.compile(
            r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}"
            r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}|LLM\|[0-9]+\|[A-Za-z0-9_-]{16,})"
        ),
    ),
    (EntityType.SSN, re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")),
    (EntityType.IBAN, re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")),
    (EntityType.IP_ADDRESS, re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
    (
        EntityType.PHONE,
        re.compile(r"(?<![\w-])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?![\w-])"),
    ),
    (
        EntityType.MONEY,
        re.compile(
            rf"(?:[$€£¥]|USD ?|EUR ?|GBP ?)\d[\d,]*(?:\.\d+)?(?: ?{MULTIPLIER}\b)?"
            rf"|\b\d[\d,]*(?:\.\d+)? ?(?:{MULTIPLIER} )?(?:dollars|USD|euros|EUR|pounds)\b"
        ),
    ),
    (
        EntityType.ADDRESS,
        re.compile(
            r"\b\d{1,6} (?:[A-Z][a-z]+ ){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Ln|Lane"
            r"|Dr|Drive|Way|Ct|Court|Pl|Place)\b\.?(?:,? (?:Apt|Suite|Unit) ?\w+)?"
        ),
    ),
    (EntityType.PROJECT, re.compile(rf"\b(?:Project|Operation|Codename|codename) {CAP}\b")),
    (EntityType.ORG, re.compile(rf"\b(?:{CAP}|[A-Z]{{2,}})(?: (?:{CAP}|[A-Z]{{2,}}|&))* {ORG_SUFFIX}\b\.?")),
    (EntityType.PERSON, re.compile(rf"\b{HONORIFICS} {CAP}(?: {CAP})?\b")),
]

_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_CAP_PAIR = re.compile(rf"\b({CAP}) ({CAP})\b")
_CAP_WORD = re.compile(r"\b[A-Z][a-zA-Z]+\b")


def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _strip_trailing_dot(text: str, start: int, end: int) -> tuple[str, int, int]:
    # "Acme Inc." at sentence end: keep the dot only if it belongs to an abbreviation.
    if text.endswith(".") and not re.search(r"(?:Inc|Corp|Ltd|Co|Dr|St|Ave|Rd|Blvd|Ln)\.$", text):
        return text[:-1], start, end - 1
    return text, start, end


def detect_rules(text: str) -> list[Entity]:
    found: list[Entity] = []
    for etype, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            value, start, end = _strip_trailing_dot(m.group(0), m.start(), m.end())
            if etype is EntityType.ORG and value.startswith("The "):
                value, start = value[4:], start + 4
            found.append(Entity(value, etype, start, end, 0.95, "rules"))

    for m in _CARD.finditer(text):
        if luhn_ok(m.group(0)):
            found.append(Entity(m.group(0), EntityType.CREDIT_CARD, m.start(), m.end(), 0.99, "rules"))

    for m in _CAP_PAIR.finditer(text):
        if m.group(1).lower() in FIRST_NAMES:
            found.append(Entity(m.group(0), EntityType.PERSON, m.start(), m.end(), 0.8, "rules"))

    for m in _CAP_WORD.finditer(text):
        if m.group(0).lower() in PUBLIC_ORGS:
            found.append(Entity(m.group(0), EntityType.ORG, m.start(), m.end(), 0.7, "rules"))

    return found


def detect_terms(text: str, terms: dict[str, EntityType]) -> list[Entity]:
    """Exact (case-insensitive, word-bounded) matches for user-taught terms."""
    found: list[Entity] = []
    for term, etype in terms.items():
        if not term.strip():
            continue
        for m in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE):
            found.append(Entity(m.group(0), etype, m.start(), m.end(), 1.0, "custom"))
    return found


def detect_context(text: str, extra_cues: Iterable[str] = ()) -> ContextSignal:
    reasons = [name for name, cue in CONFIDENTIAL_CUES.items() if re.search(cue, text, flags=re.IGNORECASE)]
    for cue in extra_cues:
        if re.search(rf"(?<!\w){re.escape(cue)}(?!\w)", text, flags=re.IGNORECASE):
            reasons.append(f"taught cue: {cue}")
    return ContextSignal(confidential=bool(reasons), reasons=reasons)
