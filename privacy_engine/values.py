"""Parsing helpers for values the policy and masker reason about."""

from __future__ import annotations

import re

_SCALE = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "trillion": 1e12,
}
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]+)?")


def parse_money(text: str) -> float | None:
    """'$1.2B' -> 1.2e9, '3 million dollars' -> 3e6, '$450,000' -> 450000.0."""
    m = _NUM.search(text)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    return value * _SCALE.get(unit, 1.0)
