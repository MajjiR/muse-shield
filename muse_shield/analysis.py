"""The model output contract: one JSON object per paragraph, validated and grounded.

The model never returns character offsets. Code finds each entity's `text` in
the paragraph by exact search, and drops entities whose text is not there
(the hallucination check). Contexts point at sentence numbers, which are
validated against the paragraph's sentence count.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

ENTITY_TYPES = {"PERSON", "ORG", "ADDRESS", "LOCATION", "AMOUNT", "PROJECT", "ID", "CONTACT"}
AMOUNT_ROLES = {"SALARY", "PRICE", "DEAL_VALUE", "LOAN", "REVENUE", "BUDGET", "FEE", "OTHER"}
CONTEXT_KINDS = {"DEAL", "DECISION", "PLAN", "NEGOTIATION", "PROJECT", "HR", "NONE"}

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def split_sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(paragraph.strip()) if s.strip()]


def number_sentences(sentences: list[str]) -> str:
    return " ".join(f"[{i}] {s}" for i, s in enumerate(sentences, 1))


@dataclass
class Span:
    text: str
    type: str
    start: int
    end: int
    role: str | None = None
    source: str = "model"


@dataclass
class Context:
    sentences: list[int]
    kind: str
    subtype: str | None = None
    refers_to: str | None = None
    summary: str = ""


@dataclass
class Analysis:
    paragraph: str
    sentences: list[str]
    entities: list[Span] = field(default_factory=list)
    contexts: list[Context] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)  # entities the model named but the text lacks
    valid: bool = True  # final output parsed and matched the contract
    attempts: int = 1
    error: str = ""
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ContractError(ValueError):
    pass


def _loads(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ContractError("top level must be an object")
    return data


def parse(raw: str, paragraph: str, sentences: list[str]) -> Analysis:
    """Validate model output against the contract. Raises ContractError if it can't be used."""
    data = _loads(raw)
    ents, ctxs = data.get("entities", []), data.get("contexts", [])
    if not isinstance(ents, list) or not isinstance(ctxs, list):
        raise ContractError("entities and contexts must be lists")

    out = Analysis(paragraph, sentences)
    for item in ents:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise ContractError(f"bad entity: {item!r:.80}")
        etype = str(item.get("type", "")).upper()
        if etype not in ENTITY_TYPES:
            raise ContractError(f"unknown entity type {etype!r}")
        role = item.get("role")
        role = str(role).upper() if role else None
        if etype == "AMOUNT" and role not in AMOUNT_ROLES:
            role = "OTHER"
        text = item["text"]
        found = [m for m in re.finditer(re.escape(text), paragraph)] if text.strip() else []
        if not found:
            out.dropped.append({"text": text, "type": etype})
            continue
        for m in found:
            out.entities.append(Span(text, etype, m.start(), m.end(), role if etype == "AMOUNT" else None))

    for item in ctxs:
        if not isinstance(item, dict):
            raise ContractError(f"bad context: {item!r:.80}")
        kind = str(item.get("kind", "")).upper()
        if kind not in CONTEXT_KINDS:
            raise ContractError(f"unknown context kind {kind!r}")
        if kind == "NONE":
            continue
        nums = item.get("sentences")
        if not isinstance(nums, list) or not nums or not all(isinstance(n, int) for n in nums):
            raise ContractError("context.sentences must be a non-empty list of ints")
        if any(n < 1 or n > len(sentences) for n in nums):
            raise ContractError(f"context.sentences {nums} out of range 1..{len(sentences)}")
        out.contexts.append(Context(
            sorted(set(nums)), kind, item.get("subtype"), item.get("refers_to"), str(item.get("summary") or ""),
        ))
    return out
