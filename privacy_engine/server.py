"""Local dashboard + API. Binds to 127.0.0.1 only: the vault reveal endpoint is for you."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .entities import EntityType
from .personalization import DeployBlocked
from .pipeline import PrivacyEngine
from .policy import Policy

WEB = Path(__file__).resolve().parent.parent / "web"


class TextIn(BaseModel):
    text: str
    conversation_id: str | None = None


class TokenIn(BaseModel):
    token: str


class TermIn(BaseModel):
    term: str
    type: EntityType = EntityType.CONFIDENTIAL_TERM


class ExampleIn(BaseModel):
    text: str
    must_mask: list[str] = []
    must_keep: list[str] = []
    type: EntityType | None = None


class DeployIn(BaseModel):
    force: bool = False


def create_app(engine: PrivacyEngine | None = None) -> FastAPI:
    engine = engine or PrivacyEngine()
    app = FastAPI(title="Privacy Engine", docs_url="/api/docs")
    app.state.engine = engine
    store = engine.store

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
        return store.set_active(policy).to_dict()

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

    # -- Teach -> Test -> Deploy ----------------------------------------------
    def teach_state() -> dict:
        return {
            "active": store.active.to_dict(),
            "draft": store.draft.to_dict() if store.draft else None,
            "diff": store.diff(),
            "examples": [e.__dict__ for e in store.examples],
            "history": [p.version for p in store.history],
        }

    def after_teach() -> dict:
        store.save()
        return teach_state()

    @app.get("/api/teach")
    def get_teach():
        return teach_state()

    @app.post("/api/teach/term")
    def teach_term(body: TermIn):
        store.teach_term(body.term, body.type)
        return after_teach()

    @app.post("/api/teach/public")
    def teach_public(body: TermIn):
        store.teach_public(body.term)
        return after_teach()

    @app.post("/api/teach/cue")
    def teach_cue(body: TermIn):
        store.teach_cue(body.term)
        return after_teach()

    @app.post("/api/teach/example")
    def teach_example(body: ExampleIn):
        store.teach_example(body.text, body.must_mask, body.must_keep, body.type)
        return after_teach()

    @app.post("/api/teach/discard")
    def discard():
        store.discard_draft()
        return after_teach()

    @app.post("/api/teach/test")
    def run_tests():
        return store.test(engine.dry_run).to_dict()

    @app.post("/api/teach/deploy")
    def deploy(body: DeployIn):
        try:
            store.deploy(store.test(engine.dry_run), force=body.force)
        except DeployBlocked as exc:
            raise HTTPException(409, str(exc)) from exc
        return teach_state()

    @app.post("/api/teach/rollback")
    def rollback():
        try:
            store.rollback()
        except DeployBlocked as exc:
            raise HTTPException(409, str(exc)) from exc
        return teach_state()

    return app
