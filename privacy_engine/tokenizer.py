"""Consistent entity tokenization backed by the vault.

The same real-world entity always gets the same token, across surface forms
and across conversations in a namespace:

    "Sarah Chen", "sarah chen", "Ms. Chen", "Sarah"   -> PERSON_1
    "Acme Corp", "Acme Corp.", "ACME"                -> ORG_1
    "$1.2B", "$1,200,000,000", "1.2 billion dollars" -> MAJOR_TRANSACTION_VALUE
    "(415) 555-0134", "415.555.0134"                 -> PHONE_1

Single-word person references only resolve when exactly one known person
shares that first or last name; otherwise they get a fresh token rather
than being silently merged with the wrong person.
"""

from __future__ import annotations

import re

from .entities import Entity, EntityType
from .masking import format_token, semantic_label
from .values import parse_money
from .vault import Vault

_HONORIFIC = re.compile(r"^(?:mr|mrs|ms|mx|dr|prof|sir|madam)\.?\s+", re.IGNORECASE)
_LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:inc|incorporated|corp|corporation|llc|llp|ltd|limited|plc|gmbh|ag|sa|co)\.?$", re.IGNORECASE
)
_DIGIT_TYPES = {EntityType.PHONE, EntityType.SSN, EntityType.CREDIT_CARD, EntityType.IP_ADDRESS}


def normalize(entity: Entity) -> str:
    text = re.sub(r"\s+", " ", entity.text.strip())
    text = re.sub(r"[’']s$", "", text)
    t = entity.type
    if t is EntityType.MONEY:
        amount = parse_money(text)
        return f"{amount:.2f}" if amount is not None else text.lower()
    if t in _DIGIT_TYPES:
        digits = re.sub(r"\D", "", text) if t is not EntityType.IP_ADDRESS else text
        if t is EntityType.PHONE and len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits
    if t is EntityType.IBAN:
        return text.replace(" ", "").upper()
    if t is EntityType.PERSON:
        text = _HONORIFIC.sub("", text)
    if t is EntityType.ORG:
        text = _LEGAL_SUFFIX.sub("", text)
    return text.casefold().strip(" .,")


class VaultAllocator:
    """TokenAllocator that persists tokens in the encrypted vault."""

    def __init__(self, vault: Vault, namespace: str = "default"):
        self.vault = vault
        self.namespace = namespace

    def _key(self, entity: Entity, canonical: str) -> str:
        return f"{entity.type.value}:{canonical}"

    def token_for(self, entity: Entity) -> str:
        canonical = normalize(entity)
        key = self._key(entity, canonical)
        token = self.vault.find(self.namespace, key)
        if token:
            return token

        if entity.type is EntityType.PERSON and " " not in canonical:
            token = self.vault.find(self.namespace, f"PERSON_PART:{canonical}")
            if token:
                self.vault.add_alias(self.namespace, key, token)
                return token

        label = semantic_label(entity)
        token = format_token(label, self.vault.next_index(self.namespace, label))
        self.vault.put(self.namespace, token, label, entity.type.value, entity.text)
        self.vault.add_alias(self.namespace, key, token)
        if entity.type is EntityType.PERSON:
            for part in canonical.split(" "):
                if len(part) > 1:
                    self.vault.add_alias(self.namespace, f"PERSON_PART:{part}", token, exclusive=True)
        return token

    def reveal(self, token: str) -> str | None:
        return self.vault.reveal(self.namespace, token)
