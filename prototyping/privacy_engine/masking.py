"""Semantic masking: swap sensitive spans for tokens that keep their meaning.

Plain redaction ("[REDACTED]") destroys the information the cloud model needs
to reason. Semantic tokens keep the role and rough magnitude:

    "Sarah Chen approved $1.2B for Project Falcon"
 -> "PERSON_1 approved MAJOR_TRANSACTION_VALUE for PROJECT_1"
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from .entities import Entity, EntityType
from .policy import Action, Decision, PolicyResult
from .values import parse_money

LABELS: dict[EntityType, str] = {
    EntityType.PERSON: "PERSON",
    EntityType.ORG: "ORG",
    EntityType.LOCATION: "LOCATION",
    EntityType.ADDRESS: "ADDRESS",
    EntityType.EMAIL: "EMAIL",
    EntityType.PHONE: "PHONE",
    EntityType.SSN: "SSN",
    EntityType.CREDIT_CARD: "CARD_NUMBER",
    EntityType.IBAN: "BANK_ACCOUNT",
    EntityType.IP_ADDRESS: "IP_ADDRESS",
    EntityType.API_KEY: "SECRET",
    EntityType.PROJECT: "PROJECT",
    EntityType.CONFIDENTIAL_TERM: "CONFIDENTIAL_TERM",
}

# (upper bound, label). Magnitude survives masking; the exact figure does not.
MONEY_BUCKETS: list[tuple[float, str]] = [
    (10_000, "SMALL_TRANSACTION_VALUE"),
    (1_000_000, "MEDIUM_TRANSACTION_VALUE"),
    (100_000_000, "LARGE_TRANSACTION_VALUE"),
    (float("inf"), "MAJOR_TRANSACTION_VALUE"),
]

# Value-class labels read naturally bare ("MAJOR_TRANSACTION_VALUE"); a second
# distinct value of the same class gets a suffix. Identity labels are always
# numbered so the cloud model can tell PERSON_1 from PERSON_2.
VALUE_CLASS_LABELS = {label for _, label in MONEY_BUCKETS}


def semantic_label(entity: Entity) -> str:
    if entity.type is EntityType.MONEY:
        amount = parse_money(entity.text)
        if amount is None:
            return "TRANSACTION_VALUE"
        return next(label for bound, label in MONEY_BUCKETS if amount < bound)
    return LABELS.get(entity.type, entity.type.value)


def format_token(label: str, n: int) -> str:
    if label in VALUE_CLASS_LABELS and n == 1:
        return label
    return f"{label}_{n}"


class TokenAllocator(Protocol):
    def token_for(self, entity: Entity) -> str: ...


class SessionAllocator:
    """In-memory allocator: identical text -> identical token within one session."""

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = defaultdict(int)
        self.originals: dict[str, str] = {}

    def token_for(self, entity: Entity) -> str:
        label = semantic_label(entity)
        key = (label, entity.text.strip().lower())
        if key not in self._by_value:
            self._counts[label] += 1
            token = format_token(label, self._counts[label])
            self._by_value[key] = token
            self.originals[token] = entity.text
        return self._by_value[key]


@dataclass
class MaskResult:
    original: str
    masked: str
    mapping: dict[str, str]  # token -> original text (never leaves the device)
    replaced: list[dict] = field(default_factory=list)
    blocked: list[Decision] = field(default_factory=list)

    def to_dict(self, include_originals: bool = False) -> dict:
        d = {
            "masked": self.masked,
            "tokens": sorted(self.mapping),
            "replaced": [{k: v for k, v in r.items() if include_originals or k != "text"} for r in self.replaced],
            "blocked": [b.entity.type.value for b in self.blocked],
        }
        if include_originals:
            d["mapping"] = self.mapping
        return d


def mask(text: str, result: PolicyResult, allocator: TokenAllocator) -> MaskResult:
    out: list[str] = []
    mapping: dict[str, str] = {}
    replaced: list[dict] = []
    cursor = 0
    for d in sorted(result.decisions, key=lambda d: d.entity.start):
        if d.action is Action.ALLOW:
            continue
        e = d.entity
        token = allocator.token_for(e)
        out.append(text[cursor : e.start])
        out.append(token)
        cursor = e.end
        mapping.setdefault(token, e.text)
        replaced.append(
            {"token": token, "text": e.text, "type": e.type.value, "sensitivity": d.sensitivity.value, "start": e.start, "end": e.end}
        )
    out.append(text[cursor:])
    return MaskResult(text, "".join(out), mapping, replaced, result.blocked)
