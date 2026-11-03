"""Call 2: Muse Spark answers over masked text and asks for hidden context through a consent step.

The model sees only placeholders. When the answer needs something hidden, it replies with
one line, NEED_CONTEXT: <LABEL> <shape|summary|full> <reason>. The engine turns that into
an ask, shows the user exactly what would be sent, and re-runs the call after an allow or
deny. A guard refuses to send any raw vault value the user hasn't explicitly allowed.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field

import httpx

from ..costs import run_cost
from .engine import Masked, Masker, rehydrate
from .vault import Vault

SYSTEM_PROMPT = """You are a helpful assistant behind a privacy gateway.
Sensitive details in the conversation were replaced on the user's device with placeholders:
- <PERSON_1>, <ORG_2>, <CONTACT_1>, <ID_1>, <ADDRESS_1>, <DATE_1>: a specific person, company, contact, ID, address or date.
- <SALARY_1>, <PRICE_1>, <DEAL_VALUE_1>, <LOAN_1>, <AMOUNT_1>: a money amount with that role.
- <DEAL_1>, <DECISION_1>, <PLAN_1>, <NEGOTIATION_1>, <PROJECT_1>, <HR_1>: a whole passage about a deal, decision, plan, negotiation, project or HR matter, hidden as one block.
Rules:
1. Treat placeholders as real values. Write them exactly as given, with the angle brackets, wherever you refer to them. Never guess or invent the real value behind one, and never invent new placeholders.
2. Answer directly whenever you can. Most requests (drafting, summarizing, explaining, planning) work fine with placeholders.
3. Only if you truly cannot answer without seeing hidden content, reply with exactly one line and nothing else:
NEED_CONTEXT: <LABEL> <level> <short reason>
where level is shape (the passage's structure with inner details still masked), summary (a one-line gist) or full (the real text).
Ask for the least you need: shape before summary before full. Ask for at most one label per reply."""

# Models sometimes drop the angle brackets ("NEED_CONTEXT: DEAL_1 summary ..."): accept both.
NEED = re.compile(r"^\s*NEED_CONTEXT:\s*<?([A-Z][A-Z_]*_\d+)>?\s+(shape|summary|full)\b\s*(.*)$", re.I | re.M)
LEVELS = ("shape", "summary", "full")


class ChatError(RuntimeError):
    pass


@dataclass
class Ask:
    ask_id: str
    chat_id: str
    label: str
    kind: str
    level: str
    reason: str
    preview: str
    previews: dict = field(default_factory=dict)  # level -> exact text that level would send
    rounds: int = 1

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("ask_id", "chat_id", "label", "kind", "level", "reason", "preview", "previews")}


@dataclass
class Turn:
    chat_id: str
    message_id: str = ""
    reply: str = ""
    masked_reply: str = ""
    sent: list[dict] = field(default_factory=list)
    ask: Ask | None = None
    masked: Masked | None = None
    error: str = ""
    cost_usd: float = 0.0
    unknown_labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"chat_id": self.chat_id, "message_id": self.message_id, "reply": self.reply, "masked_reply": self.masked_reply,
                "sent": self.sent, "ask": self.ask.to_dict() if self.ask else None,
                "masked": self.masked.to_dict() if self.masked else None, "error": self.error,
                "cost_usd": self.cost_usd, "unknown_labels": self.unknown_labels}


def find_leaks(payload: str, secrets: dict[str, str]) -> list[str]:
    hay = payload.casefold()
    return [label for label, v in secrets.items()
            if len(v.strip()) >= 3 and (v.strip().casefold() in hay or json.dumps(v.strip())[1:-1].casefold() in hay)]


class ChatModel:
    """Plain chat completions on the Meta Model API (Standard tier only)."""

    def __init__(self, base_url: str, model: str, api_key: str, client: httpx.Client | None = None,
                 reasoning_effort: str = "low", max_tokens: int = 4096, timeout: float = 180.0):
        if "contributor" in model:
            raise ChatError(f"{model} lets Meta train on prompts; the app only allows Standard models")
        if not api_key:
            raise ChatError("missing MODEL_API_KEY")
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.client, self.reasoning_effort, self.max_tokens, self.timeout = client or httpx.Client(), reasoning_effort, max_tokens, timeout

    def complete(self, messages: list[dict]) -> tuple[str, dict]:
        payload = {"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": self.max_tokens}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        for attempt in range(4):
            try:
                r = self.client.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout,
                                     headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.HTTPError as exc:
                raise ChatError(str(exc)) from exc
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            break
        if r.status_code != 200:
            raise ChatError(f"chat model returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        return (data["choices"][0]["message"].get("content") or "").strip(), data.get("usage") or {}


class ChatEngine:
    def __init__(self, vault: Vault, masker: Masker, model: ChatModel, max_ask_rounds: int = 2, inspector=None):
        self.vault, self.masker, self.model, self.max_rounds = vault, masker, model, max_ask_rounds
        self.inspector = inspector
        self.pending: dict[str, Ask] = {}
        self.masks: dict[str, Masked] = {}  # mask previews, so Mask & send doesn't analyze twice

    # -- conversation building -------------------------------------------------
    def _history(self, chat_id: str) -> list[dict]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in self.vault.messages(chat_id):
            if m["role"] in ("user", "assistant"):
                msgs.append({"role": m["role"], "content": m["masked_text"]})
            elif m["role"] == "reveal":
                msgs.append({"role": "user", "content": m["original"] or m["masked_text"]})
        return msgs

    def _allowed(self, chat_id: str) -> set[str]:
        """Labels whose real values the user explicitly let through (a full context allows its members too)."""
        allowed = {c["label"] for c in self.vault.consents(chat_id) if c["decision"] == "allow" and c["level"] == "full"}
        for label in list(allowed):
            allowed.update(self.vault.members(chat_id, label))
        return allowed

    def _send(self, chat_id: str, turn: Turn) -> None:
        messages = self._history(chat_id)
        payload = json.dumps(messages, ensure_ascii=False)
        mapping = self.vault.mapping(chat_id)
        allowed = self._allowed(chat_id)
        secrets = {label: value for label, value in mapping.items() if label not in allowed}
        leaks = find_leaks(payload, secrets)
        if leaks:
            raise ChatError(f"refusing to send: raw values for {', '.join(leaks)} are in the outbound messages")
        t0 = time.perf_counter()
        if self.inspector:
            self.inspector.for_chat(chat_id)
        content, usage = self.model.complete(messages)
        tokens = {"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                  "cached_in": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}
        turn.cost_usd += run_cost(self.model.model, tokens, time.perf_counter() - t0)["usd"] or 0.0
        turn.sent = messages

        need = NEED.search(content)
        if need and turn.ask is None:
            label, level, reason = f"<{need.group(1).upper()}>", need.group(2).lower(), need.group(3).strip()
            if label not in mapping:
                # Don't show the request line as an answer, and don't store it in the conversation.
                turn.error = f"Muse Spark asked for {label}, which isn't in this chat's vault. Try rephrasing."
                return
            target = self.vault._target(chat_id, label)
            kind = "context" if target and target[0] == "context" else "entity"
            if kind == "entity":
                level = "full"  # an entity has only its value
            levels = LEVELS if kind == "context" else ("full",)
            previews = {lv: self.vault.resolve(chat_id, label, lv) for lv in levels}
            ask = Ask("a_" + uuid.uuid4().hex[:10], chat_id, label, kind, level, reason, previews[level], previews)
            self.pending[ask.ask_id] = ask
            turn.ask = ask
            self.vault.audit("ask", chat_id, {"asks": 1})
            return
        # A normal answer (or an unusable NEED_CONTEXT line): store and rehydrate.
        turn.masked_reply = content
        turn.reply, turn.unknown_labels = rehydrate(content, mapping)
        turn.message_id = self.vault.add_message(chat_id, "assistant", content, meta={"cost_usd": turn.cost_usd})

    # -- public ---------------------------------------------------------------
    def preview(self, text: str, chat_id: str | None) -> tuple[str, Masked]:
        chat_id = self.vault.ensure_chat(chat_id)
        masked = self.masker.mask(text, chat_id)
        mask_id = "k_" + uuid.uuid4().hex[:10]
        self.masks[mask_id] = masked
        return mask_id, masked

    def chat(self, message: str, chat_id: str | None = None, mask_id: str | None = None) -> Turn:
        cached = self.masks.pop(mask_id, None) if mask_id else None
        if cached and cached.original == message:
            chat_id, masked = cached.chat_id, cached
        else:
            chat_id = self.vault.ensure_chat(chat_id)
            masked = self.masker.mask(message, chat_id)
        turn = Turn(chat_id, masked=masked, cost_usd=masked.cost_usd or 0.0)
        if not masked.analysis_ok:
            turn.error = f"Not sent: {masked.error}"
            return turn
        # Spans keep offsets and types only: their text is the real value, and meta is stored unencrypted.
        spans = [{k: v for k, v in sp.items() if k != "text"} for sp in masked.spans]
        self.vault.add_message(chat_id, "user", masked.masked_text, original=message,
                               meta={"spans": spans, "cost_usd": masked.cost_usd})
        try:
            self._send(chat_id, turn)
        except ChatError as exc:
            turn.error = str(exc)
        return turn

    def reveal(self, ask_id: str, decision: str, level: str | None = None) -> Turn:
        ask = self.pending.pop(ask_id, None)
        if ask is None:
            raise ChatError("unknown or already answered ask")
        if level and level != ask.level and ask.kind == "context":
            ask.level, ask.preview = level, self.vault.resolve(ask.chat_id, ask.label, level)
        self.vault.consent(ask.chat_id, ask.label, ask.level, decision, ask.reason)
        if decision == "allow":
            note = f"[The user allowed you to see {ask.label} ({ask.level})]: {ask.preview}"
        else:
            note = f"[The user declined to reveal {ask.label}. Answer as well as you can without it, keeping placeholders.]"
        meta = {"label": ask.label, "level": ask.level, "decision": decision}
        if decision == "allow" and ask.level == "full":
            # The note holds real text: keep it encrypted, store only a stub in the clear column.
            self.vault.add_message(ask.chat_id, "reveal", f"[{ask.label} revealed in full]", original=note, meta=meta)
        else:
            self.vault.add_message(ask.chat_id, "reveal", note, meta=meta)
        turn = Turn(ask.chat_id)
        try:
            self._send(ask.chat_id, turn)
        except ChatError as exc:
            turn.error = str(exc)
        if turn.ask is not None:  # the model asked again: allow one more round, then stop asking
            turn.ask.rounds = ask.rounds + 1
            if turn.ask.rounds > self.max_rounds:
                self.pending.pop(turn.ask.ask_id, None)
                turn.ask = None
                turn.error = "the model kept asking for more context; stopped"
        return turn
