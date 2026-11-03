"""Ensemble detector: rules + taught terms + optional local Llama."""

from __future__ import annotations

import logging

from ..entities import ContextSignal, Detection, Entity, EntityType
from .llm import LlamaDetector
from .rules import detect_context, detect_rules, detect_terms

log = logging.getLogger(__name__)

# When spans overlap, the more trustworthy source wins; then the longer span.
_SOURCE_RANK = {"custom": 3, "rules": 2, "llm": 1}
# Structured identifiers from regex+checksum beat anything the LLM says.
_STRUCTURED = {
    EntityType.EMAIL, EntityType.PHONE, EntityType.SSN, EntityType.CREDIT_CARD,
    EntityType.IBAN, EntityType.IP_ADDRESS, EntityType.API_KEY, EntityType.MONEY,
}


def _rank(e: Entity) -> tuple:
    return (e.type in _STRUCTURED, _SOURCE_RANK.get(e.source, 0), e.end - e.start, e.score)


def merge(entities: list[Entity]) -> list[Entity]:
    kept: list[Entity] = []
    for e in sorted(entities, key=_rank, reverse=True):
        if not any(e.overlaps(k) for k in kept):
            kept.append(e)
    return sorted(kept, key=lambda e: e.start)


class Detector:
    def __init__(self, llama: LlamaDetector | None = None):
        self.llama = llama

    def detect(
        self,
        text: str,
        terms: dict[str, EntityType] | None = None,
        cues: list[str] | None = None,
        use_llm: bool = True,
    ) -> Detection:
        entities = detect_rules(text) + detect_terms(text, terms or {})
        context = detect_context(text, cues or [])
        backends = ["rules"]

        if use_llm and self.llama is not None and self.llama.available():
            try:
                llm_entities, llm_context = self.llama.detect(text)
                entities += llm_entities
                context = ContextSignal(
                    context.confidential or llm_context.confidential,
                    context.reasons + llm_context.reasons,
                )
                backends.append(self.llama.name)
            except Exception as exc:  # local model hiccup must never block the request
                log.warning("local llama detector failed, using rules only: %s", exc)

        return Detection(text, merge(entities), context, backends)


__all__ = ["Detector", "LlamaDetector", "merge"]
