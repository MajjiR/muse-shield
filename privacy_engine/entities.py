"""Shared types: what the detector finds and how sensitive it is."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORG = "ORG"
    LOCATION = "LOCATION"
    ADDRESS = "ADDRESS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    IBAN = "IBAN"
    IP_ADDRESS = "IP_ADDRESS"
    API_KEY = "API_KEY"
    MONEY = "MONEY"
    PROJECT = "PROJECT"
    CONFIDENTIAL_TERM = "CONFIDENTIAL_TERM"


class Sensitivity(str, Enum):
    PII = "PII"
    CONFIDENTIAL = "CONFIDENTIAL"
    PUBLIC = "PUBLIC"


@dataclass
class Entity:
    text: str
    type: EntityType
    start: int
    end: int
    score: float = 1.0
    source: str = "rules"

    def overlaps(self, other: "Entity") -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "type": self.type.value,
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 3),
            "source": self.source,
        }


@dataclass
class ContextSignal:
    """Document-level read on whether the text discusses confidential business."""

    confidential: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"confidential": self.confidential, "reasons": self.reasons}


@dataclass
class Detection:
    text: str
    entities: list[Entity]
    context: ContextSignal
    backends: list[str]

    def to_dict(self) -> dict:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "context": self.context.to_dict(),
            "backends": self.backends,
        }
