"""FastAPI app on 127.0.0.1 (localhost only: it can decrypt the vault)."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..backends import Backend, BackendError, MetaModelBackend
from ..config import load_env
from .chat import ChatEngine, ChatError, ChatModel, find_leaks
from .engine import Masker, rehydrate, segments
from .inspector import Inspector, user_text
from .schemas import ChatRequest, MaskRequest, RevealRequest, UnmaskRequest, VaultRevealRequest
from .vault import Vault

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "dist"  # the built React app (npm run build in apps/web)
META_URL = "https://api.meta.ai/v1"


def analyzer_from_env(client: httpx.Client | None = None) -> tuple[Backend | None, str]:
    """Call 1 analyzer: Muse Spark Standard. Returns (backend or None, reason it's off)."""
    load_env()
    model = os.environ.get("MUSE_SHIELD_MODEL", "muse-spark-1.3")
    if "contributor" in model:
        return None, f"{model} lets Meta train on prompts; the app only allows Standard models"
    if os.environ.get("MUSE_SHIELD_DEV_RAW_ANALYSIS") != "1":
        return None, ("analysis is off: call 1 sends raw text to Meta. Set MUSE_SHIELD_DEV_RAW_ANALYSIS=1 "
                      "to enable it for fake data while prototyping")
    try:
        # Analysis runs on every message, so default to minimal reasoning for chat-speed latency.
        effort = os.environ.get("MUSE_SHIELD_ANALYSIS_EFFORT", "minimal")
        return MetaModelBackend(os.environ.get("META_BASE_URL", META_URL), model, os.environ.get("MODEL_API_KEY", ""),
                                name="muse_spark", synthetic_only=True, reasoning_effort=effort, client=client), ""
    except BackendError as exc:
        return None, str(exc)


def chat_model_from_env(client: httpx.Client | None = None) -> tuple[ChatModel | None, str]:
    load_env()
    try:
        return ChatModel(os.environ.get("META_BASE_URL", META_URL), os.environ.get("MUSE_SHIELD_CHAT_MODEL", "muse-spark-1.3"),
                         os.environ.get("MODEL_API_KEY", ""), client=client,
                         reasoning_effort=os.environ.get("MUSE_SHIELD_CHAT_EFFORT", "low")), ""
    except ChatError as exc:
        return None, str(exc)


def create_app(vault: Vault | None = None, analyzer: Backend | None = None, chat_model: ChatModel | None = None,
               inspector: Inspector | None = None) -> FastAPI:
    inspector = inspector or Inspector()
    off_reason = chat_off = ""
    if analyzer is None:
        analyzer, off_reason = analyzer_from_env(inspector.client("analysis"))
    if chat_model is None:
        chat_model, chat_off = chat_model_from_env(inspector.client("chat"))
    vault = vault or Vault.open()
    masker = Masker(vault, analyzer) if analyzer else None
    engine = ChatEngine(vault, masker, chat_model, inspector=inspector) if masker and chat_model else None

    app = FastAPI(title="Muse Shield", version=__version__, docs_url="/docs")
    # The React dev server (and later the Electron renderer) call the engine from another local origin.
    origins = os.environ.get("MUSE_SHIELD_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins if o.strip()],
                       allow_methods=["GET", "POST"], allow_headers=["content-type"])
    app.state.vault, app.state.masker, app.state.engine, app.state.inspector = vault, masker, engine, inspector

    def need_chat(chat_id: str) -> None:
        if not any(c["chat_id"] == chat_id for c in vault.chats()):
            raise HTTPException(404, f"unknown chat {chat_id}")

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "analysis": bool(masker), "chat": bool(engine),
                "analysis_model": getattr(analyzer, "model", None), "chat_model": getattr(chat_model, "model", None),
                "analysis_off_reason": off_reason, "chat_off_reason": chat_off}

    @app.post("/mask")
    def mask(body: MaskRequest):
        if not masker:
            chat_id = vault.ensure_chat(body.chat_id)
            return {"chat_id": chat_id, "masked_text": body.text, "spans": [], "contexts": [], "analysis_ok": False,
                    "error": off_reason, "latency_ms": 0, "cost_usd": None, "mask_id": None}
        if engine:
            mask_id, masked = engine.preview(body.text, body.chat_id)
            return {**masked.to_dict(), "mask_id": mask_id}
        chat_id = vault.ensure_chat(body.chat_id)
        return {**masker.mask(body.text, chat_id).to_dict(), "mask_id": None}

    @app.post("/unmask")
    def unmask(body: UnmaskRequest):
        need_chat(body.chat_id)
        text, unknown = rehydrate(body.text, vault.mapping(body.chat_id))
        return {"text": text, "unknown": unknown}

    @app.post("/chat")
    def chat(body: ChatRequest):
        if not engine:
            raise HTTPException(503, off_reason or chat_off or "chat unavailable")
        return engine.chat(body.message, body.chat_id, body.mask_id).to_dict()

    @app.post("/reveal")
    def reveal(body: RevealRequest):
        if not engine:
            raise HTTPException(503, "chat unavailable")
        try:
            return engine.reveal(body.ask_id, body.decision, body.level).to_dict()
        except ChatError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/chats")
    def chats():
        return vault.chats()

    @app.post("/chats")
    def new_chat():
        return {"chat_id": vault.create_chat()}

    @app.get("/chats/{chat_id}")
    def chat_detail(chat_id: str):
        need_chat(chat_id)
        mapping = vault.mapping(chat_id, contexts="summary")  # assistant text: a hidden passage shows as its summary
        msgs = []
        for m in vault.messages(chat_id):
            shown = m["original"] if m["role"] == "user" else rehydrate(m["masked_text"], mapping)[0]
            extra = {"segments": segments(m["masked_text"], chat_id, vault)} if m["role"] == "assistant" else {}
            if m["role"] == "reveal":
                m = {**m, "original": None}  # the note's text is for the model; the UI shows the consent itself
            msgs.append({**m, "text": shown, **extra})
        return {"chat_id": chat_id, "messages": msgs, "consents": vault.consents(chat_id)}

    @app.get("/chats/{chat_id}/vault")
    def chat_vault(chat_id: str):
        need_chat(chat_id)
        return vault.items(chat_id)

    @app.post("/vault/reveal")
    def vault_reveal(body: VaultRevealRequest):
        need_chat(body.chat_id)
        value = vault.resolve(body.chat_id, body.label)
        if value is None:
            raise HTTPException(404, "unknown placeholder")
        vault.audit("local_reveal", body.chat_id, {"labels": 1})
        return {"label": body.label, "value": value}

    @app.get("/chats/{chat_id}/graph")
    def chat_graph(chat_id: str):
        need_chat(chat_id)
        return vault.graph(chat_id)

    @app.get("/inspector")
    def inspect():
        return {"summary": inspector.summary(), "requests": inspector.list()}

    @app.get("/inspector/audit")
    def leak_audit():
        """Scan every chat (masked) request for raw vault values its chat never allowed."""
        leaks, scanned, checks = [], 0, 0
        for r in inspector.list():
            cid = r.get("chat_id")
            if r["purpose"] != "chat" or not cid:
                continue
            allowed = engine._allowed(cid) if engine else set()
            secrets = {k: v for k, v in vault.mapping(cid).items() if k not in allowed}
            scanned += 1
            checks += len(secrets)
            found = find_leaks(user_text(r["request_body"]), secrets)
            if found:
                leaks.append({"request": r["id"], "chat_id": cid, "labels": found})
        return {"chat_requests_scanned": scanned, "checks": checks, "leaks": leaks, "clean": not leaks}

    @app.get("/metrics")
    def metrics():
        counts: dict[str, int] = {}
        cost_by_chat: dict[str, float] = {}
        for row in vault.audit_rows():
            if row["event"] == "mask":
                for k, v in row["counts"].items():
                    counts[k] = counts.get(k, 0) + v
        for chat in vault.chats():
            total = sum((m["meta"] or {}).get("cost_usd") or 0 for m in vault.messages(chat["chat_id"]))
            cost_by_chat[chat["chat_id"]] = round(total, 6)
        consents = vault.consents()
        return {"masked_by_type": counts, "asks": sum(1 for r in vault.audit_rows() if r["event"] == "ask"),
                "consents": {"allow": sum(c["decision"] == "allow" for c in consents), "deny": sum(c["decision"] == "deny" for c in consents)},
                "cost_by_chat": cost_by_chat, "cost_total": round(sum(cost_by_chat.values()), 6), "inspector": inspector.summary()}

    if (WEB / "assets").exists():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/")
    def index():
        page = WEB / "index.html"
        return FileResponse(page) if page.exists() else {"ok": True, "hint": "UI not built: cd apps/web && npm run build"}

    return app
