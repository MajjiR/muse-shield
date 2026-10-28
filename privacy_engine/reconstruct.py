"""Local response reconstruction: put the real values back, on-device.

Cloud models mostly keep tokens verbatim, but not always. This tolerates
the usual drift (case changes, [PERSON_1], <PERSON_1>, **PERSON_1**) and
reports tokens it could not resolve, such as a PERSON_9 the model invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

TOKEN_SHAPE = re.compile(
    r"\b(?:[A-Z]+_)*(?:PERSON|ORG|PROJECT|EMAIL|PHONE|ADDRESS|LOCATION|SECRET|SSN|CARD_NUMBER|BANK_ACCOUNT"
    r"|IP_ADDRESS|CONFIDENTIAL_TERM|TRANSACTION_VALUE)(?:_\d+)?\b"
)


@dataclass
class Reconstruction:
    text: str
    restored: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "restored": self.restored, "unresolved": self.unresolved}


def _variant_pattern(token: str) -> re.Pattern[str]:
    core = re.escape(token)
    # Optional wrapping the model may add: [T], <T>, {T}, **T**, `T`
    return re.compile(rf"(?:\[|<|\{{|\*\*|`)?(?<![A-Za-z0-9_]){core}(?![A-Za-z0-9_])(?:\]|>|\}}|\*\*|`)?", re.IGNORECASE)


def reconstruct(
    text: str,
    mapping: dict[str, str],
    fallback: Callable[[str], str | None] | None = None,
) -> Reconstruction:
    """Replace tokens with originals. mapping wins; fallback (the vault) covers older turns."""
    known = dict(mapping)
    for candidate in set(TOKEN_SHAPE.findall(text.upper())):
        if candidate not in known and fallback is not None:
            value = fallback(candidate)
            if value is not None:
                known[candidate] = value

    restored: list[str] = []
    # Longest first so MAJOR_TRANSACTION_VALUE_2 is not eaten by MAJOR_TRANSACTION_VALUE.
    for token in sorted(known, key=len, reverse=True):
        pattern = _variant_pattern(token)
        text, n = pattern.subn(lambda _m, v=known[token]: v, text)
        if n:
            restored.append(token)

    unresolved = sorted(set(TOKEN_SHAPE.findall(text)))
    return Reconstruction(text, sorted(restored), unresolved)
