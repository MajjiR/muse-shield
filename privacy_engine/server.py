"""Local dashboard + API. Binds to 127.0.0.1 only: the vault reveal endpoint is for you."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .pipeline import PrivacyEngine
from .policy import Policy, save_policy

WEB = Path(__file__).resolve().parent.parent / "web"


class TextIn(BaseModel):
    text: str
    conversation_id: str | None = None


class TokenIn(BaseModel):
    token: str


def create_app(engine: PrivacyEngine | None = None) -> FastAPI:
    engine = engine or PrivacyEngine()
    app = FastAPI(title="Privacy Engine", docs_url="/api/docs")
    app.state.engine = engine

    def persist_policy() -> None:
        save_policy(engine.policy, engine.settings.ensure_home() / "policy.json")

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/status")
    def status():
        llama = engine.detector.llama
        return {
            "local_model": llama.model if llama else None,
            "local_model_up": bool(llama and llama.available()),
            "local_model_latency_ms": llama.last_latency_ms if llama else None,
            "cloud": engine.cloud.name,
            "cloud_mock": engine.cloud.mock,
            "vault_entries": len(engine.vault.entries(engine.namespace)),
            "inspector": engine.inspector.summary(),
            "policy_version": engine.policy.version,
        }

    @app.post("/api/protect")
    def protect(body: TextIn):
        return engine.protect(body.text).to_dict()

    @app.post("/api/ask")
    def ask(body: TextIn):
        return engine.ask(body.text, body.conversation_id).to_dict()

    @app.get("/api/policy")
    def get_policy():
        return engine.policy.to_dict()

    @app.put("/api/policy")
    def put_policy(body: dict):
        try:
            policy = Policy.from_dict(body)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, f"invalid policy: {exc}") from exc
        engine.policy = policy
        persist_policy()
        return engine.policy.to_dict()

    @app.get("/api/vault")
    def vault():
        return [e.to_dict() for e in engine.vault.entries(engine.namespace)]

    @app.post("/api/vault/reveal")
    def reveal(body: TokenIn):
        value = engine.allocator.reveal(body.token)
        if value is None:
            raise HTTPException(404, "unknown token")
        return {"token": body.token, "value": value}

    @app.delete("/api/vault")
    def wipe_vault():
        engine.vault.wipe(engine.namespace)
        engine.conversations.clear()
        return {"ok": True}

    @app.get("/api/inspector")
    def inspector():
        return {"summary": engine.inspector.summary(), "records": [r.to_dict() for r in reversed(engine.inspector.records)]}

    @app.delete("/api/inspector")
    def clear_inspector():
        engine.inspector.clear()
        return {"ok": True}

    return app
