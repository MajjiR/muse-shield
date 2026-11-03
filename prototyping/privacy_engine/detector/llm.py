"""On-device Llama (~1B) detector for names, orgs, codenames and confidential context.

Rules catch structured identifiers; a small instruction-tuned Llama catches the
things regexes can't: free-form names, company names without a suffix, project
codenames, and whether the passage is confidential business context.

Every span the model returns is re-located in the source text, so a
hallucinated entity can never be masked into (or leak out of) the prompt.
"""

from __future__ import annotations

import json
import re
import time

import httpx

from ..entities import ContextSignal, Entity, EntityType
from ..llm_client import LLMError, chat

SYSTEM_PROMPT = """You are a privacy filter running on the user's device.
Find every span in the user's text that is private or confidential:
- PERSON: names of people
- ORG: companies, funds, teams, customers
- LOCATION: cities, sites, home locations tied to a person
- PROJECT: internal project or product codenames
- CONFIDENTIAL_TERM: deal terms, unreleased product names, internal metrics
Copy each span EXACTLY as it appears. Do not invent spans.
Also decide if the text discusses confidential business (deals, M&A, unreleased plans, internal numbers).
Reply with JSON only:
{"entities": [{"text": "...", "type": "PERSON"}], "confidential": true, "reason": "..."}"""

FEW_SHOT_USER = "Can you draft a note to Priya Shah at Northwind about Project Falcon closing next week?"
FEW_SHOT_ASSISTANT = json.dumps(
    {
        "entities": [
            {"text": "Priya Shah", "type": "PERSON"},
            {"text": "Northwind", "type": "ORG"},
            {"text": "Project Falcon", "type": "PROJECT"},
        ],
        "confidential": True,
        "reason": "internal project closing timeline",
    }
)

ALLOWED = {EntityType.PERSON, EntityType.ORG, EntityType.LOCATION, EntityType.PROJECT, EntityType.CONFIDENTIAL_TERM}
_STOP = frozenset("i me my we our you your the a an it this that he she they them user assistant".split())


class LlamaDetector:
    """Calls a local OpenAI-compatible endpoint (Ollama by default)."""

    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None, timeout: float = 30.0):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._client = client or httpx.Client()
        self._available: bool | None = None
        self._checked_at = 0.0
        self.last_latency_ms: float | None = None

    @property
    def name(self) -> str:
        return f"llama:{self.model}"

    def available(self) -> bool:
        # Re-probe at most every 30s so starting Ollama mid-demo is picked up.
        if self._available is not None and time.monotonic() - self._checked_at < 30:
            return self._available
        try:
            r = self._client.get(f"{self.base_url.rstrip('/')}/models", timeout=1.5)
            self._available = r.status_code == 200
        except httpx.HTTPError:
            self._available = False
        self._checked_at = time.monotonic()
        return self._available

    def detect(self, text: str) -> tuple[list[Entity], ContextSignal]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": FEW_SHOT_USER},
            {"role": "assistant", "content": FEW_SHOT_ASSISTANT},
            {"role": "user", "content": text},
        ]
        t0 = time.perf_counter()
        try:
            raw = chat(self._client, self.base_url, self.model, messages, json_mode=True, timeout=self.timeout)
        except LLMError:
            self._available = False
            raise
        finally:
            self.last_latency_ms = (time.perf_counter() - t0) * 1000
        return parse_response(raw, text)


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}


def parse_response(raw: str, text: str) -> tuple[list[Entity], ContextSignal]:
    data = _extract_json(raw)
    entities: list[Entity] = []
    for item in data.get("entities") or []:
        if not isinstance(item, dict):
            continue
        span = str(item.get("text", "")).strip().strip(".,;:'\"")
        try:
            etype = EntityType(str(item.get("type", "")).upper())
        except ValueError:
            continue
        if etype not in ALLOWED or len(span) < 2 or span.lower() in _STOP:
            continue
        # Grounding: only keep spans that literally occur in the input.
        for m in re.finditer(rf"(?<!\w){re.escape(span)}(?!\w)", text):
            entities.append(Entity(m.group(0), etype, m.start(), m.end(), 0.75, "llm"))

    confidential = bool(data.get("confidential"))
    reason = str(data.get("reason") or "").strip()
    context = ContextSignal(confidential, [f"llm: {reason}"] if confidential and reason else [])
    return entities, context
