"""Routes for the Chrome extension that shields meta.ai (apps/extension).

The extension replaces Call 2: instead of the engine calling Muse Spark, the user's
masked message is typed into meta.ai by the extension, and Meta AI's reply is read back
from the page. The engine still does Call 1 (analysis), the vault, rehydration and consent.

    /ext/bind     meta.ai conversation id <-> vault chat (ids only, no values)
    /ext/preview  what would be masked, for underlines while you type (writes nothing to the vault)
    /ext/mask     mask a message, with your keep / extra overrides; returns the exact text for meta.ai
    /ext/restore  rehydrate a reply that is still streaming (nothing stored)
    /ext/reply    a finished reply: store it, or turn a NEED_CONTEXT line into an ask
    /ext/consent  allow or deny an ask; returns the note to send to Meta AI

Only the extension's own pages (side panel) call these: content scripts can't reach
localhost, so meta.ai's page never sees a real value.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..analysis import ENTITY_TYPES, Analysis, split_sentences
from .chat import LEVELS, NEED, find_leaks
from .engine import ALWAYS_MASK, Masked, Masker, paragraphs, rehydrate, segments, sentence_offsets
from .vault import Vault

# Sent once, ahead of the first message of every shielded meta.ai chat (meta.ai has no system prompt).
PREAMBLE = """[Muse Shield privacy note. Please follow it for this whole chat.]
Sensitive details in my messages were replaced on my device with placeholders: <PERSON_1>, <ORG_1>, <CONTACT_1>, <ID_1>, <ADDRESS_1>, <DATE_1> are a person, company, contact, ID, address or date; <SALARY_1>, <PRICE_1>, <DEAL_VALUE_1>, <AMOUNT_1> are money amounts with that role; <DEAL_1>, <DECISION_1>, <PLAN_1>, <NEGOTIATION_1>, <PROJECT_1>, <HR_1> are whole hidden passages.
1. Treat placeholders as the real values and write them exactly as given, with the angle brackets. Never guess what is behind one and never invent new ones.
2. Answer directly whenever you can: drafting, summarizing and planning work fine with placeholders.
3. Only if you truly cannot answer without hidden content, reply with exactly one line and nothing else:
NEED_CONTEXT: <LABEL> <shape|summary|full> <short reason>
(shape = the passage with inner details still masked, summary = a one-line gist, full = the real text). Ask for the least you need.
[End of note. My message follows.]"""

_BARE = re.compile(r"(?<![<\w\[])\[?([A-Z][A-Z_]*_\d+)\]?(?![>\w])")


def normalize_labels(text: str, mapping: dict[str, str]) -> str:
    """Meta AI sometimes writes [PERSON_1] or PERSON_1: map those back to <PERSON_1> when the vault knows the label."""
    return _BARE.sub(lambda m: f"<{m.group(1)}>" if f"<{m.group(1)}>" in mapping else m.group(0), text)


class CachedAnalyzer:
    """Remembers each paragraph's analysis, so sending right after a live preview costs no second call."""

    def __init__(self, inner, size: int = 256):
        self.inner, self.size = inner, size
        self.model, self.name = getattr(inner, "model", ""), getattr(inner, "name", "analyzer")
        self._cache: OrderedDict[str, Analysis] = OrderedDict()
        self._lock = threading.Lock()

    def analyze(self, paras: list[str], known_labels: list[str] | None = None) -> list[Analysis]:
        out = []
        for p in paras:
            with self._lock:
                hit = self._cache.get(p)
                if hit is not None:
                    self._cache.move_to_end(p)
            if hit is not None:
                out.append(dataclasses.replace(hit, usage={}, latency_ms=0.0))  # already paid for
                continue
            a = self.inner.analyze([p], known_labels)[0]
            if a.valid:
                with self._lock:
                    self._cache[p] = a
                    while len(self._cache) > self.size:
                        self._cache.popitem(last=False)
            out.append(a)
        return out


def preview_spans(text: str, analyses: list[Analysis]) -> list[dict]:
    """Detected entities and context blocks with offsets into text, without minting placeholders."""
    out = []
    for (off, para), a in zip(paragraphs(text), analyses):
        sentences = a.sentences or split_sentences(para) or [para]
        offs = sentence_offsets(para, sentences)
        for c in a.contexts:
            lo, hi = min(c.sentences), max(c.sentences)
            start, end = off + offs[lo - 1][0], off + offs[hi - 1][1]
            out.append({"kind": "context", "type": c.kind, "role": None, "start": start, "end": end, "text": text[start:end],
                        "summary": c.summary, "policy": False})
        for e in a.entities:
            out.append({"kind": "entity", "type": e.type, "role": e.role, "start": off + e.start, "end": off + e.end, "text": e.text,
                        "summary": "", "policy": e.type in ALWAYS_MASK})
    return sorted(out, key=lambda s: (s["start"], -s["end"]))


def apply_overrides(vault: Vault, chat_id: str, masked: Masked, keep: set[str], extra: list[dict]) -> tuple[str, list[dict]]:
    """Rebuild the masked text with your choices: kept spans go as written (hard-rule types can't be kept;
    a kept passage still hides the entities inside it), extra spans get placeholders like any other."""
    text = masked.original
    ctx = {s["placeholder"]: s for s in masked.spans if s["kind"] == "context"}
    kept_ctx = {label for label, s in ctx.items() if s["text"] in keep}
    reps, spans = [], []
    for s in masked.spans:
        s = dict(s)
        if s["kind"] == "context":
            s["kept"] = s["placeholder"] in kept_ctx
            if not s["kept"]:
                reps.append((s["start"], s["end"], s["placeholder"]))
        else:
            s["kept"] = s["text"] in keep and s["type"] not in ALWAYS_MASK
            swallowed = s.get("in_context") and s["in_context"] not in kept_ctx
            if not s["kept"] and not swallowed:
                reps.append((s["start"], s["end"], s["placeholder"]))
            if s["kept"]:
                s["placeholder"] = None
        spans.append(s)
    for x in extra:
        value, etype = x.get("text", ""), (x.get("type") or "ID").upper()
        if not value.strip() or etype not in ENTITY_TYPES:
            continue
        label = None
        for m in re.finditer(re.escape(value), text):
            if any(m.start() < e and b < m.end() for b, e, _ in reps):
                continue
            label = label or vault.entity_placeholder(chat_id, etype, value)[0]
            reps.append((m.start(), m.end(), label))
            spans.append({"start": m.start(), "end": m.end(), "text": value, "type": etype, "role": None, "placeholder": label,
                          "kind": "entity", "source": "user", "in_context": None, "kept": False})
    pieces, cursor = [], 0
    for start, end, label in sorted(reps):
        pieces += [text[cursor:start], label]
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces), spans


class Bindings:
    """meta.ai conversation id -> vault chat id. Ids only; kept next to the vault."""

    def __init__(self, vault: Vault):
        path = ":memory:" if vault.path == ":memory:" else str(Path(vault.path).with_name("extension.db"))
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS bindings (site TEXT NOT NULL, conversation_id TEXT NOT NULL, "
                         "chat_id TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (site, conversation_id))")

    def get(self, site: str, conversation_id: str) -> str | None:
        row = self._db.execute("SELECT chat_id FROM bindings WHERE site=? AND conversation_id=?", (site, conversation_id)).fetchone()
        return row[0] if row else None

    def set(self, site: str, conversation_id: str, chat_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?,?)", (site, conversation_id, chat_id, time.time()))


class BindRequest(BaseModel):
    site: str = "meta.ai"
    conversation_id: str | None = None  # None on a new meta.ai chat, before its first message
    chat_id: str | None = None  # the vault chat already used for this tab, to bind once meta.ai assigns an id


class ExtPreviewRequest(BaseModel):
    text: str


class ExtMaskRequest(BaseModel):
    text: str
    chat_id: str | None = None
    keep: list[str] = []  # span texts you chose to send as written
    extra: list[dict] = []  # [{"text", "type"}] spans you chose to mask


class ExtReplyRequest(BaseModel):
    chat_id: str
    text: str  # the reply exactly as meta.ai shows it (masked)
    message_id: str | None = None  # meta.ai's id for the reply, so a re-read doesn't store it twice


class ExtConsentRequest(BaseModel):
    chat_id: str
    label: str
    level: str
    decision: str
    reason: str = ""


def history(vault: Vault, chat_id: str) -> list[dict]:
    """The chat as the side panel shows it: your words, and Meta AI's replies restored."""
    out = []
    for m in vault.messages(chat_id):
        if m["role"] == "user":
            out.append({"role": "user", "text": m["original"], "masked": m["meta"].get("outbound") or m["masked_text"],
                        "spans": m["meta"].get("spans", [])})
        elif m["role"] == "assistant":
            out.append({"role": "assistant", "masked": m["masked_text"], "segments": segments(m["masked_text"], chat_id, vault),
                        "site_message_id": m["meta"].get("site_message_id")})
        elif m["role"] == "reveal":
            out.append({"role": "reveal", **{k: m["meta"].get(k) for k in ("label", "level", "decision")}})
    return out


def add_extension_routes(app: FastAPI, vault: Vault, masker: Masker | None, off_reason: str) -> None:
    bindings = Bindings(vault)
    seen_replies: dict[str, set[str]] = {}
    cached = CachedAnalyzer(masker.analyzer) if masker else None
    masker = Masker(vault, cached, masker.workers) if masker else None

    def need_chat(chat_id: str) -> None:
        if not any(c["chat_id"] == chat_id for c in vault.chats()):
            raise HTTPException(404, f"unknown chat {chat_id}")

    def allowed(chat_id: str) -> set[str]:
        out = {c["label"] for c in vault.consents(chat_id) if c["decision"] == "allow" and c["level"] == "full"}
        for label in list(out):
            out.update(vault.members(chat_id, label))
        return out

    def leaks(chat_id: str, outbound: str) -> list[str]:
        keep = allowed(chat_id)
        return find_leaks(outbound, {k: v for k, v in vault.mapping(chat_id).items() if k not in keep})

    @app.post("/ext/bind")
    def bind(body: BindRequest):
        chat_id = bindings.get(body.site, body.conversation_id) if body.conversation_id else None
        if chat_id is None and body.chat_id and body.conversation_id:
            need_chat(body.chat_id)
            bindings.set(body.site, body.conversation_id, body.chat_id)
            chat_id = body.chat_id
        return {"chat_id": chat_id, "messages": history(vault, chat_id) if chat_id else [],
                "analysis": bool(masker), "analysis_off_reason": off_reason}

    @app.post("/ext/preview")
    def preview(body: ExtPreviewRequest):
        if not masker:
            raise HTTPException(503, off_reason or "analysis unavailable")
        t0 = time.perf_counter()
        paras = paragraphs(body.text)
        try:
            analyses = masker._analyze(paras)
        except Exception as exc:  # noqa: BLE001 - shown as "couldn't check" in the composer
            return {"ok": False, "error": str(exc), "spans": []}
        bad = [a for a in analyses if not a.valid]
        if bad:
            return {"ok": False, "error": bad[0].error, "spans": []}
        return {"ok": True, "error": "", "spans": preview_spans(body.text, analyses),
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}

    @app.post("/ext/mask")
    def ext_mask(body: ExtMaskRequest):
        if not masker:
            raise HTTPException(503, off_reason or "analysis unavailable")
        chat_id = vault.ensure_chat(body.chat_id, title="meta.ai chat")
        first = not any(m["role"] == "user" for m in vault.messages(chat_id))
        masked = masker.mask(body.text, chat_id)
        if not masked.analysis_ok:
            return {**masked.to_dict(), "outbound": None, "first": first, "leaks": []}
        masked_text, spans = apply_overrides(vault, chat_id, masked, set(body.keep), body.extra)
        outbound = f"{PREAMBLE}\n\n{masked_text}" if first else masked_text
        kept = {s["text"] for s in spans if s.get("kept")}
        found = [label for label in leaks(chat_id, outbound) if vault.resolve(chat_id, label) not in kept]
        if found:  # a value masked elsewhere is still in the text: don't send
            return {**masked.to_dict(), "analysis_ok": False, "error": f"raw values for {', '.join(found)} are still in the text",
                    "outbound": None, "first": first, "leaks": found}
        stored = [{k: v for k, v in s.items() if k != "text"} for s in spans]
        vault.add_message(chat_id, "user", masked_text, original=body.text,
                          meta={"spans": stored, "cost_usd": masked.cost_usd, "site": "meta.ai", "outbound": outbound})
        return {**masked.to_dict(), "masked_text": masked_text, "spans": spans, "outbound": outbound, "first": first, "leaks": []}

    @app.post("/ext/restore")
    def restore(body: ExtReplyRequest):
        need_chat(body.chat_id)
        text = normalize_labels(body.text, vault.mapping(body.chat_id))
        return {"segments": segments(text, body.chat_id, vault)}

    @app.post("/ext/reply")
    def reply(body: ExtReplyRequest):
        need_chat(body.chat_id)
        mapping = vault.mapping(body.chat_id)
        text = normalize_labels(body.text.strip(), mapping)
        need = NEED.search(text)
        if need:
            label, level, reason = f"<{need.group(1).upper()}>", need.group(2).lower(), need.group(3).strip()
            target = vault._target(body.chat_id, label)
            if target is None:
                return {"ask": None, "segments": segments(text, body.chat_id, vault),
                        "error": f"Meta AI asked for {label}, which isn't in this chat's vault"}
            kind = "context" if target[0] == "context" else "entity"
            levels = LEVELS if kind == "context" else ("full",)
            if kind == "entity":
                level = "full"
            vault.audit("ask", body.chat_id, {"asks": 1})
            return {"ask": {"chat_id": body.chat_id, "label": label, "kind": kind, "level": level, "reason": reason,
                            "previews": {lv: vault.resolve(body.chat_id, label, lv) for lv in levels}},
                    "segments": [], "error": ""}
        seen = seen_replies.setdefault(body.chat_id, set())
        if not body.message_id or body.message_id not in seen:
            vault.add_message(body.chat_id, "assistant", text, meta={"site": "meta.ai", "site_message_id": body.message_id})
            if body.message_id:
                seen.add(body.message_id)
        _, unknown = rehydrate(text, mapping)
        return {"ask": None, "segments": segments(text, body.chat_id, vault), "unknown": unknown, "error": ""}

    @app.post("/ext/consent")
    def consent(body: ExtConsentRequest):
        need_chat(body.chat_id)
        if body.decision not in ("allow", "deny") or body.level not in LEVELS:
            raise HTTPException(422, "decision must be allow|deny and level shape|summary|full")
        preview = vault.resolve(body.chat_id, body.label, body.level)
        if preview is None:
            raise HTTPException(404, "unknown placeholder")
        vault.consent(body.chat_id, body.label, body.level, body.decision, body.reason)
        if body.decision == "allow":
            note = f"[I allowed you to see {body.label} ({body.level})]: {preview}"
        else:
            note = f"[I declined to reveal {body.label}. Answer as well as you can without it, keeping placeholders.]"
        meta = {"label": body.label, "level": body.level, "decision": body.decision, "site": "meta.ai"}  # meta is stored in the clear
        if body.decision == "allow" and body.level == "full":
            vault.add_message(body.chat_id, "reveal", f"[{body.label} revealed in full]", original=note, meta=meta)
        else:
            vault.add_message(body.chat_id, "reveal", note, meta=meta)
        found = leaks(body.chat_id, note)
        if found:
            raise HTTPException(409, f"refusing: raw values for {', '.join(found)} are in the note")
        return {"outbound": note}
