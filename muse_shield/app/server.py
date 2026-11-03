"""FastAPI app on 127.0.0.1 (localhost only: it can decrypt the vault)."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..backends import Backend, BackendError, MetaModelBackend
from ..config import load_env
from .engine import Masker, rehydrate
from .schemas import MaskRequest, UnmaskRequest, VaultRevealRequest
from .vault import Vault

WEB = Path(__file__).resolve().parents[2] / "web"


def analyzer_from_env() -> tuple[Backend | None, str]:
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
        return MetaModelBackend(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), model,
                                os.environ.get("MODEL_API_KEY", ""), name="muse_spark", synthetic_only=True,
                                reasoning_effort=effort), ""
    except BackendError as exc:
        return None, str(exc)


def create_app(vault: Vault | None = None, analyzer: Backend | None = None, analyzer_off_reason: str = "") -> FastAPI:
    if analyzer is None and not analyzer_off_reason:
        analyzer, analyzer_off_reason = analyzer_from_env()
    vault = vault or Vault.open()
    masker = Masker(vault, analyzer) if analyzer else None

    app = FastAPI(title="Muse Shield", version=__version__, docs_url="/docs")
    app.state.vault, app.state.masker = vault, masker

    def need_chat(chat_id: str) -> None:
        if not any(c["chat_id"] == chat_id for c in vault.chats()):
            raise HTTPException(404, f"unknown chat {chat_id}")

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "analysis": bool(masker),
                "analysis_model": getattr(analyzer, "model", None), "analysis_off_reason": analyzer_off_reason}

    @app.post("/mask")
    def mask(body: MaskRequest):
        chat_id = vault.ensure_chat(body.chat_id, title=body.text[:40] or "New chat")
        if not masker:
            return {"chat_id": chat_id, "masked_text": body.text, "spans": [], "contexts": [], "analysis_ok": False,
                    "error": analyzer_off_reason, "latency_ms": 0, "cost_usd": None}
        return masker.mask(body.text, chat_id).to_dict()

    @app.post("/unmask")
    def unmask(body: UnmaskRequest):
        need_chat(body.chat_id)
        text, unknown = rehydrate(body.text, vault.mapping(body.chat_id))
        return {"text": text, "unknown": unknown}

    @app.get("/chats")
    def chats():
        return vault.chats()

    @app.post("/chats")
    def new_chat():
        return {"chat_id": vault.create_chat()}

    @app.get("/chats/{chat_id}")
    def chat(chat_id: str):
        need_chat(chat_id)
        return {"chat_id": chat_id, "messages": vault.messages(chat_id)}

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

    if WEB.exists():
        app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def index():
        page = WEB / "index.html"
        return FileResponse(page) if page.exists() else {"ok": True, "hint": "web UI not built yet"}

    return app
