"""Cloud gateway: the only code path that talks to a remote LLM.

Three guarantees, each independent of the others:
1. Callers hand it masked messages only (the pipeline never passes raw text).
2. EgressGuard serializes the exact request body and refuses to send it if any
   original sensitive value (from this request's vault mapping) appears in it.
3. NetworkInspector records every byte that actually left the process, via
   httpx event hooks, and re-scans it for leaks after the fact.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import httpx

from .llm_client import chat
from .reconstruct import TOKEN_SHAPE

CLOUD_SYSTEM_PROMPT = """Some values in the user's messages were replaced on their device with placeholder tokens \
such as PERSON_1, ORG_2, PROJECT_1, EMAIL_1 or MAJOR_TRANSACTION_VALUE.
Treat each token as an opaque real value. Whenever you refer to that value, write the token exactly as given: \
same spelling, no brackets, no quotes. Never guess or invent the real value behind a token, and never invent new tokens.
Money tokens tell you magnitude: SMALL_TRANSACTION_VALUE < $10k, MEDIUM < $1M, LARGE < $100M, MAJOR >= $100M."""


class PrivacyViolation(RuntimeError):
    """Raised when an outbound payload still contains a raw sensitive value."""


def find_leaks(payload: str, secrets: dict[str, str]) -> list[str]:
    """Return tokens whose original value appears in payload (raw or JSON-escaped)."""
    haystack = payload.casefold()
    number_runs = [re.sub(r"\D", "", run) for run in re.findall(r"\d[\d\s().-]{5,}\d", payload)]
    leaked = []
    for token, value in secrets.items():
        v = value.strip()
        if len(v) < 3:
            continue
        if any(c in haystack for c in (v.casefold(), json.dumps(v)[1:-1].casefold())):
            leaked.append(token)
            continue
        # Phone / card / SSN numbers: also catch a reformatted copy ("415.555.0134").
        if re.fullmatch(r"[\d\s().+-]{7,}", v):
            digits = re.sub(r"\D", "", v)
            if len(digits) >= 7 and any(digits[-10:] in run for run in number_runs):
                leaked.append(token)
    return leaked


@dataclass
class EgressRecord:
    id: str
    ts: float
    method: str
    url: str
    request_bytes: int
    request_body: str
    status: int | None = None
    response_body: str = ""
    latency_ms: float | None = None
    conversation_id: str = ""
    tokens_sent: list[str] = field(default_factory=list)
    leaked_tokens: list[str] = field(default_factory=list)
    mock: bool = False

    @property
    def clean(self) -> bool:
        return not self.leaked_tokens

    def to_dict(self) -> dict:
        return {**asdict(self), "clean": self.clean}


class NetworkInspector:
    """Captures everything sent to the cloud. Stores only what was on the wire."""

    def __init__(self, log_path: Path | None = None, keep: int = 500):
        self.records: deque[EgressRecord] = deque(maxlen=keep)
        self.log_path = log_path
        self._lock = threading.Lock()
        self._pending: dict[int, EgressRecord] = {}
        self._context = threading.local()

    def set_context(self, conversation_id: str, secrets: dict[str, str], mock: bool) -> None:
        self._context.value = (conversation_id, secrets, mock)

    def _ctx(self) -> tuple[str, dict[str, str], bool]:
        return getattr(self._context, "value", ("", {}, False))

    def on_request(self, request: httpx.Request) -> None:
        body = request.content.decode("utf-8", "replace")
        conv, secrets, mock = self._ctx()
        rec = EgressRecord(
            id=uuid.uuid4().hex[:12],
            ts=time.time(),
            method=request.method,
            url=str(request.url),
            request_bytes=len(request.content),
            request_body=body,
            conversation_id=conv,
            tokens_sent=sorted(set(TOKEN_SHAPE.findall(_user_text(body))) & set(secrets)),
            leaked_tokens=find_leaks(body, secrets),
            mock=mock,
        )
        request.extensions["egress_started"] = time.perf_counter()
        with self._lock:
            self._pending[id(request)] = rec

    def on_response(self, response: httpx.Response) -> None:
        response.read()
        with self._lock:
            rec = self._pending.pop(id(response.request), None)
        if rec is None:
            return
        rec.status = response.status_code
        rec.response_body = response.text
        started = response.request.extensions.get("egress_started")
        if started:
            rec.latency_ms = (time.perf_counter() - started) * 1000
        self._store(rec)

    def _store(self, rec: EgressRecord) -> None:
        with self._lock:
            self.records.append(rec)
            if self.log_path:
                with self.log_path.open("a") as f:
                    f.write(json.dumps(rec.to_dict()) + "\n")

    def summary(self) -> dict:
        recs = list(self.records)
        return {
            "requests": len(recs),
            "bytes_sent": sum(r.request_bytes for r in recs),
            "clean": sum(r.clean for r in recs),
            "leaks": sum(not r.clean for r in recs),
            "tokens_sent": sum(len(r.tokens_sent) for r in recs),
        }

    def clear(self) -> None:
        with self._lock:
            self.records.clear()


def _user_text(body: str) -> str:
    try:
        return " ".join(m.get("content", "") for m in json.loads(body).get("messages", []) if m.get("role") != "system")
    except (ValueError, AttributeError):
        return body


# -- offline mock cloud -------------------------------------------------------

def mock_cloud_reply(messages: list[dict]) -> str:
    """A deterministic stand-in for the cloud model, so demos run offline."""
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    tokens = list(dict.fromkeys(TOKEN_SHAPE.findall(last)))
    people = [t for t in tokens if t.startswith("PERSON")]
    others = [t for t in tokens if not t.startswith("PERSON")]
    lower = last.lower()
    if any(w in lower for w in ("email", "draft", "note", "message", "write")):
        to = people[-1] if people else "team"
        lines = [f"Hi {to},", "", "Following up on our discussion"]
        if others:
            lines[-1] += " regarding " + ", ".join(others)
        lines[-1] += ". I wanted to confirm next steps and timing; let me know what works on your side."
        lines += ["", "Best,", people[0] if len(people) > 1 else "[your name]"]
        return "\n".join(lines)
    if tokens:
        return (
            "Here's a summary of the key points:\n"
            + "\n".join(f"- {t} is central to this request." for t in tokens)
            + "\n\nI've kept every placeholder as-is so it can be restored on your device."
        )
    return "Understood. (offline mock cloud: set CLOUD_API_KEY to use a real model)"


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            content = mock_cloud_reply(body.get("messages", []))
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


# -- gateway ------------------------------------------------------------------


class CloudLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        inspector: NetworkInspector | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.inspector = inspector or NetworkInspector()
        self.mock = not api_key and transport is None
        if self.mock:
            self.base_url = "https://mock-cloud.invalid/v1"
            transport = _mock_transport()
        self._client = httpx.Client(
            transport=transport,
            event_hooks={"request": [self.inspector.on_request], "response": [self.inspector.on_response]},
        )

    @property
    def name(self) -> str:
        return "mock-cloud" if self.mock else f"{self.base_url} · {self.model}"

    def complete(
        self,
        masked_messages: list[dict[str, str]],
        secrets: dict[str, str],
        conversation_id: str = "",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        messages = [{"role": "system", "content": CLOUD_SYSTEM_PROMPT}, *masked_messages]
        guard(messages, secrets)
        self.inspector.set_context(conversation_id, secrets, self.mock)
        return chat(
            self._client, self.base_url, self.model, messages,
            api_key=self.api_key, temperature=temperature, max_tokens=max_tokens,
        )


def guard(messages: Iterable[dict], secrets: dict[str, str]) -> None:
    payload = json.dumps(list(messages), ensure_ascii=False)
    leaked = find_leaks(payload, secrets)
    if leaked:
        raise PrivacyViolation(f"refusing to send: raw values for {', '.join(leaked)} present in outbound payload")
