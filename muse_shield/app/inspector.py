"""Every request that leaves the engine, captured from the real httpx request objects.

Two purposes are tagged so the UI can prove the split:
    analysis  call 1, raw text (development only)
    chat      call 2, masked text plus anything the user explicitly allowed
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque

import httpx


class Inspector:
    def __init__(self, keep: int = 300):
        self.records: deque[dict] = deque(maxlen=keep)
        self._lock = threading.Lock()
        self._local = threading.local()

    def for_chat(self, chat_id: str | None) -> None:
        """Tag requests made on this thread with a chat id (kept locally, never sent)."""
        self._local.chat_id = chat_id

    def client(self, purpose: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
        def on_request(request: httpx.Request) -> None:
            request.extensions["muse_t0"] = time.perf_counter()
            request.extensions["muse_chat"] = getattr(self._local, "chat_id", None)

        def on_response(response: httpx.Response) -> None:
            response.read()
            req = response.request
            body = req.content.decode("utf-8", "replace")
            try:
                usage = response.json().get("usage") or {}
            except ValueError:
                usage = {}
            rec = {
                "id": uuid.uuid4().hex[:10], "ts": time.time(), "purpose": purpose, "chat_id": req.extensions.get("muse_chat"),
                "method": req.method,
                "url": str(req.url), "bytes": len(req.content), "status": response.status_code,
                "latency_ms": round((time.perf_counter() - req.extensions.get("muse_t0", time.perf_counter())) * 1000, 1),
                "request_body": body, "response_body": response.text[:20000], "usage": usage,
            }
            with self._lock:
                self.records.append(rec)

        return httpx.Client(transport=transport, event_hooks={"request": [on_request], "response": [on_response]})

    def list(self) -> list[dict]:
        with self._lock:
            return list(reversed(self.records))

    def summary(self) -> dict:
        recs = self.list()
        by = lambda p: [r for r in recs if r["purpose"] == p]  # noqa: E731
        return {"requests": len(recs), "analysis_requests": len(by("analysis")), "chat_requests": len(by("chat")),
                "bytes_sent": sum(r["bytes"] for r in recs)}


def user_text(body: str) -> str:
    """The non-system message text of a chat-completions body (what the leak audit scans)."""
    try:
        return "\n".join(m.get("content", "") for m in json.loads(body).get("messages", []) if m.get("role") != "system")
    except (ValueError, AttributeError):
        return body
