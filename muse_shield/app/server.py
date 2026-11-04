"""FastAPI app on 127.0.0.1 (localhost only: it can decrypt the vault)."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, documents
from ..backends import Backend, BackendError, GlimmerBackend
from ..config import load_env
from ..agent.executor import Executor
from ..connectors.personal import channel_names
from ..agent.tools import catalog
from ..images import ImageMasker, image_models_from_env
from .chat import ChatEngine, ChatError, ChatModel, find_leaks
from .documents import add_document_routes
from .connections_api import add_connection_routes
from .images_api import add_image_routes
from .engine import MODES, Masker, ModeError, ModeMasker, rehydrate, segments
from .extension import add_extension_routes
from .inspector import Inspector, user_text
from .schemas import ChatRequest, ImageMaskRequest, MaskRequest, NewChatRequest, RevealRequest, UnmaskRequest, VaultRevealRequest
from .vault import Vault

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "dist"  # the built React app (npm run build in apps/web)
META_URL = "https://api.meta.ai/v1"


def analyzer_from_env(client: httpx.Client | None = None) -> tuple[Backend | None, str]:
    """Call 1 analyzer: our fine-tuned Muse Glimmer (MUSE_SHIELD_ANALYZER=glimmer + MUSE_SHIELD_GLIMMER_MODEL).
    Cloud Muse Spark no longer finds what to mask; it only answers over masked text. Returns (backend, why off)."""
    load_env()
    if os.environ.get("MUSE_SHIELD_ANALYZER") == "glimmer":
        return glimmer_analyzer_from_env(client)
    return None, ("masking runs on the fine-tuned Muse Glimmer: start the app with `python -m muse_shield.app`, which "
                  "brings up the masking model, or set MUSE_SHIELD_GLIMMER_ER_MODEL to a running deployment")


def glimmer_analyzer_from_env(client: httpx.Client | None = None) -> tuple[Backend | None, str]:
    """Muse Glimmer 30B with a Muse Shield LoRA, on the user's own Fireworks deployment.

    MUSE_SHIELD_GLIMMER_TASK=resolution uses an entity-resolution LoRA (er-v2a) instead of a stage-1 one.
    MUSE_SHIELD_GLIMMER_MODEL is the full route '<model>#<deployment>', e.g.
    accounts/<a>/models/muse-shield-glimmer-lora-v2-full#accounts/<a>/deployments/<id> (a live-merge
    deployment needs both full paths). Raw text goes to that dedicated deployment, so the same
    made-up-data gate as Spark applies. A deployment that scaled to zero answers 503 SCALING_UP;
    the backend waits for it (cold start is a few minutes).
    """
    model = os.environ.get("MUSE_SHIELD_GLIMMER_MODEL", "")
    if "#" not in model:
        return None, ("MUSE_SHIELD_ANALYZER=glimmer needs MUSE_SHIELD_GLIMMER_MODEL=<model>#<deployment> "
                      "(a fine-tuned LoRA is served only from an on-demand deployment)")
    if os.environ.get("MUSE_SHIELD_DEV_RAW_ANALYSIS") != "1":
        return None, ("analysis is off: call 1 sends raw text to the Glimmer deployment. Set "
                      "MUSE_SHIELD_DEV_RAW_ANALYSIS=1 to enable it for fake data while prototyping")
    key = os.environ.get("GLIMMER_API_KEY") or os.environ.get("FIREWORKS_API_KEY", "")
    if not key:
        return None, "MUSE_SHIELD_ANALYZER=glimmer needs FIREWORKS_API_KEY"
    base = os.environ.get("GLIMMER_BASE_URL", "https://api.fireworks.ai/inference/v1")
    if os.environ.get("MUSE_SHIELD_GLIMMER_TASK") == "resolution":
        # An entity-resolution LoRA (er-*): one call per message, one identity per person, owners and relations.
        # It speaks the resolution contract (muse_shield/resolution.py), not the stage-1 paragraph contract.
        from ..resolution import ResolutionAnalyzer
        return ResolutionAnalyzer(GlimmerBackend(base, model, key, client=client, max_tokens=4000, timeout=300.0)), ""
    return GlimmerBackend(base, model, key, client=client), ""


def _mode_entries(analyzer) -> dict[str, tuple[Backend, bool]]:
    """The masking modes one analyzer provides: (analyzer, classify flag) per mode."""
    if hasattr(analyzer, "classify_document"):  # entity-resolution Glimmer: plain, or with the classify prompt
        return {"resolution": (analyzer, False), "resolution_classify": (analyzer, True)}
    if isinstance(analyzer, GlimmerBackend):  # stage-1 Glimmer LoRA: entities + context blocks per paragraph
        return {"pii_context": (analyzer, False)}
    return {"custom": (analyzer, False)}  # an analyzer passed in directly (tests, embedders)


def modes_from_env(client: httpx.Client | None = None) -> tuple[dict[str, tuple[Backend, bool]], str, str]:
    """All masking modes this server runs: (mode -> (analyzer, classify), default mode, reason analysis is off).

    MUSE_SHIELD_GLIMMER_PII_MODEL and MUSE_SHIELD_GLIMMER_ER_MODEL (each '<model>#<deployment>') run the stage-1
    Glimmer (PII + context) and the entity-resolution Glimmer side by side; without them, the single analyzer from
    analyzer_from_env() decides. MUSE_SHIELD_DEFAULT_MODE picks the mode new chats start in.
    """
    load_env()
    pii, er = os.environ.get("MUSE_SHIELD_GLIMMER_PII_MODEL", ""), os.environ.get("MUSE_SHIELD_GLIMMER_ER_MODEL", "")
    modes: dict[str, tuple[Backend, bool]] = {}
    off = ""
    if pii or er:
        if os.environ.get("MUSE_SHIELD_DEV_RAW_ANALYSIS") != "1":
            return {}, "", ("analysis is off: call 1 sends raw text to the Glimmer deployments. Set "
                            "MUSE_SHIELD_DEV_RAW_ANALYSIS=1 to enable it for fake data while prototyping")
        key = os.environ.get("GLIMMER_API_KEY") or os.environ.get("FIREWORKS_API_KEY", "")
        base = os.environ.get("GLIMMER_BASE_URL", "https://api.fireworks.ai/inference/v1")
        if not key:
            return {}, "", "the Glimmer modes need FIREWORKS_API_KEY"
        if "#" in pii:
            modes.update(_mode_entries(GlimmerBackend(base, pii, key, client=client)))
        if "#" in er:
            from ..resolution import ResolutionAnalyzer
            modes.update(_mode_entries(ResolutionAnalyzer(GlimmerBackend(base, er, key, client=client, max_tokens=4000, timeout=300.0))))
        if not modes:
            off = "MUSE_SHIELD_GLIMMER_PII_MODEL / _ER_MODEL must be full routes '<model>#<deployment>'"
    else:
        analyzer, off = analyzer_from_env(client)
        if analyzer:
            modes = _mode_entries(analyzer)
    default = os.environ.get("MUSE_SHIELD_DEFAULT_MODE", "")
    return modes, default if default in modes else next(iter(modes), ""), off


def image_text_check(client: httpx.Client | None = None):
    """Opt-in (MUSE_SHIELD_IMAGE_TEXT_CHECK=1): SAM can't read, so our Glimmer deployment looks at each masked image and
    answers one question: private text still showing? Without a Glimmer deployment every image is then refused."""
    from ..images import GlimmerTextCheck

    route = os.environ.get("MUSE_SHIELD_GLIMMER_ER_MODEL") or os.environ.get("MUSE_SHIELD_GLIMMER_PII_MODEL", "")
    key = os.environ.get("GLIMMER_API_KEY") or os.environ.get("FIREWORKS_API_KEY", "")
    try:
        return GlimmerTextCheck(os.environ.get("GLIMMER_BASE_URL", "https://api.fireworks.ai/inference/v1"), route, key,
                                client=client)
    except BackendError as exc:
        def refuse(image: bytes, mime: str):
            raise BackendError(str(exc))
        return refuse


def chat_model_from_env(client: httpx.Client | None = None) -> tuple[ChatModel | None, str]:
    load_env()
    try:
        return ChatModel(os.environ.get("META_BASE_URL", META_URL), os.environ.get("MUSE_SHIELD_CHAT_MODEL", "muse-spark-1.3"),
                         os.environ.get("MODEL_API_KEY", ""), client=client,
                         reasoning_effort=os.environ.get("MUSE_SHIELD_CHAT_EFFORT", "low")), ""
    except ChatError as exc:
        return None, str(exc)


def create_app(vault: Vault | None = None, analyzer: Backend | None = None, chat_model: ChatModel | None = None,
               inspector: Inspector | None = None, image_masker: ImageMasker | None = None,
               documents_sync: bool = False, modes: dict | None = None, default_mode: str | None = None) -> FastAPI:
    inspector = inspector or Inspector()
    off_reason = chat_off = ""
    if modes:  # tests and embedders: {mode: (analyzer, classify)}
        default_mode = default_mode if default_mode in modes else next(iter(modes))
    elif analyzer is None:
        modes, default_mode, off_reason = modes_from_env(inspector.client("analysis"))
    else:
        modes = _mode_entries(analyzer)
        default_mode = next(iter(modes))
    if chat_model is None:
        chat_model, chat_off = chat_model_from_env(inspector.client("chat"))
    vault = vault or Vault.open()
    # One Masker per analyzer; each chat is locked to one mode (ModeMasker routes by the chat's stored mode).
    # Your chat channel names are workspace structure, never masked.
    maskers: dict[int, Masker] = {}
    masker_for = {m: (maskers.setdefault(id(a), Masker(vault, a, public=channel_names)), classify) for m, (a, classify) in modes.items()}
    masker = ModeMasker(vault, masker_for, default_mode) if masker_for else None
    analyzer = masker.analyzer if masker else None
    executor = Executor(vault, masker=masker)
    engine = ChatEngine(vault, masker, chat_model, inspector=inspector, executor=executor) if masker and chat_model else None
    images_off = ""
    if image_masker is None:
        vision, sam, images_off = image_models_from_env(inspector.client("image"))
        concepts = [c.strip() for c in os.environ.get("MUSE_SHIELD_SAM_CONCEPTS", "").split(",") if c.strip()] or None
        # SAM 3.1 covers faces, plates, cards, documents and codes. Blocking images that still show other text is
        # opt-in (MUSE_SHIELD_IMAGE_TEXT_CHECK=1): our Glimmer then looks at the masked picture before it's sent.
        check = os.environ.get("MUSE_SHIELD_IMAGE_TEXT_CHECK") == "1" and not vision
        image_masker = ImageMasker(vault, vision, sam, concepts=concepts,
                                   text_check=image_text_check(inspector.client("image")) if check else None) if (vision or sam) else None

    app = FastAPI(title="Muse Shield", version=__version__, docs_url="/docs")
    # The React dev server (and later the Electron renderer) call the engine from another local origin.
    origins = os.environ.get("MUSE_SHIELD_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins if o.strip()],
                       allow_methods=["GET", "POST"],
                       allow_headers=["content-type", "x-filename", "x-chat-id"], expose_headers=["content-disposition"])
    app.state.vault, app.state.masker, app.state.engine, app.state.inspector = vault, masker, engine, inspector
    app.state.executor = executor

    def need_chat(chat_id: str) -> None:
        if not any(c["chat_id"] == chat_id for c in vault.chats()):
            raise HTTPException(404, f"unknown chat {chat_id}")

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "analysis": bool(masker), "chat": bool(engine),
                "analysis_model": getattr(analyzer, "model", None), "chat_model": getattr(chat_model, "model", None),
                "analysis_off_reason": off_reason, "chat_off_reason": chat_off,
                "images": bool(image_masker), "images_off_reason": images_off, "documents": documents.available(),
                # Masking modes this server runs; each chat is locked to one (POST /chats {"mode": ...}).
                "modes": [{"id": m, "label": MODES[m]["label"], "detail": MODES[m]["detail"],
                           "model": getattr(masker.masker_for[m][0].analyzer, "model", None)} for m in masker.modes] if masker else [],
                "default_mode": masker.default if masker else None,
                # Image masking uses two models: Muse Spark reads the picture, SAM 3.1 outlines faces and plates.
                "image_model": " + ".join(m.model for m in (image_masker.vision, image_masker.sam) if m) if image_masker else None}

    @app.post("/mask")
    def mask(body: MaskRequest):
        if not masker:
            chat_id = vault.ensure_chat(body.chat_id)
            return {"chat_id": chat_id, "masked_text": body.text, "spans": [], "contexts": [], "analysis_ok": False,
                    "error": off_reason, "latency_ms": 0, "cost_usd": None, "mask_id": None}
        try:
            if engine:
                mask_id, masked = engine.preview(body.text, body.chat_id, body.mode)
                return {**masked.to_dict(), "mask_id": mask_id}
            chat_id = vault.ensure_chat(body.chat_id)
            return {**masker.mask(body.text, chat_id, mode=body.mode).to_dict(), "mask_id": None}
        except ModeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/images/mask")
    def mask_image(body: ImageMaskRequest):
        """Faces blurred, sensitive text covered with its vault placeholder. Returns the masked PNG."""
        if not image_masker:
            raise HTTPException(503, images_off or "image masking is off")
        raw = body.image.split(",", 1)[1] if body.image.startswith("data:") else body.image
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "image must be base64 or a data: URL")
        if len(data) > 20_000_000:
            raise HTTPException(413, "image over 20 MB")
        try:
            return image_masker.mask(data, body.chat_id, verify=body.verify).to_dict()
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except BackendError as exc:
            raise HTTPException(502, str(exc))

    @app.post("/unmask")
    def unmask(body: UnmaskRequest):
        need_chat(body.chat_id)
        text, unknown = rehydrate(body.text, vault.mapping(body.chat_id))
        return {"text": text, "unknown": unknown}

    @app.post("/chat")
    def chat(body: ChatRequest):
        if not engine:
            raise HTTPException(503, off_reason or chat_off or "chat unavailable")
        return engine.chat(body.message, body.chat_id, body.mask_id, body.document_ids, body.image_ids, body.mode).to_dict()

    @app.post("/reveal")
    def reveal(body: RevealRequest):
        if not engine:
            raise HTTPException(503, "chat unavailable")
        try:
            items = {k: v.model_dump() for k, v in body.items.items()} if body.items else None
            return engine.reveal(body.ask_id, body.decision, body.level, items).to_dict()
        except ChatError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/chats")
    def chats():
        return vault.chats()

    @app.post("/chats")
    def new_chat(body: NewChatRequest | None = None):
        mode = body.mode if body else None
        try:
            mode = masker.check(mode) if masker else None
        except ModeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"chat_id": vault.create_chat(mode=mode), "mode": mode}

    @app.post("/chats/{chat_id}/delete")
    def delete_chat(chat_id: str):
        removed = vault.delete_chat(chat_id)
        if removed is None:
            raise HTTPException(404, "unknown chat")
        return {"ok": True, "removed": removed}

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
            if m["role"] == "document":  # shown as a card, not the whole (rehydrated) document
                msgs.append({**m, "masked_text": "", "text": "", "document": vault.document(m["meta"].get("doc_id", ""))})
                continue
            if m["role"] == "image":
                msgs.append({**m, "masked_text": "", "text": "", "image": vault.image(m["meta"].get("image_id", ""))})
                continue
            msgs.append({**m, "text": shown, **extra})
        return {"chat_id": chat_id, "messages": msgs, "consents": vault.consents(chat_id), "mode": vault.chat_mode(chat_id)}

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

    # -- agent actions ------------------------------------------------------------
    @app.get("/agent/tools")
    def agent_tools():
        return catalog()

    @app.post("/agent/execute")
    def agent_execute(body: dict):
        """Run a placeholder tool call directly (agents, tests). Side-effect tools come back pending."""
        chat_id = body.get("chat_id") or ""
        need_chat(chat_id)
        return executor.propose(chat_id, str(body.get("tool", "")), body.get("args") or {}).for_user()

    @app.post("/agent/actions/{action_id}/{decision}")
    def agent_decide(action_id: str, decision: str):
        if decision not in ("confirm", "deny"):
            raise HTTPException(404, "use confirm or deny")
        if engine and engine.owns(action_id):  # proposed by the chat model: continue that conversation
            try:
                return (engine.confirm_action if decision == "confirm" else engine.deny_action)(action_id).to_dict()
            except ChatError as exc:
                raise HTTPException(404, str(exc)) from exc
        try:
            a = executor.confirm(action_id) if decision == "confirm" else executor.deny(action_id)
        except KeyError as exc:
            raise HTTPException(404, "unknown or already handled action") from exc
        return {"chat_id": a.chat_id, "action": a.for_user()}

    @app.get("/chats/{chat_id}/actions")
    def chat_actions(chat_id: str):
        """Tool calls in this chat, oldest first, so the UI can restore a pending confirmation after a reload."""
        need_chat(chat_id)
        return [a.for_user() for a in sorted(executor.actions.values(), key=lambda a: a.created_at) if a.chat_id == chat_id]

    @app.get("/chats/{chat_id}/outbox")
    def chat_outbox(chat_id: str):
        need_chat(chat_id)
        return vault.outbox(chat_id)

    @app.get("/vault/audit/verify")
    def audit_verify():
        return vault.verify_audit()

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
        already_sent = counts.pop("ALREADY_SENT", 0)  # seen unmasked on an earlier turn, so not masked
        return {"masked_by_type": counts, "already_sent": already_sent, "asks": sum(1 for r in vault.audit_rows() if r["event"] == "ask"),
                "consents": {"allow": sum(c["decision"] == "allow" for c in consents), "deny": sum(c["decision"] == "deny" for c in consents)},
                "cost_by_chat": cost_by_chat, "cost_total": round(sum(cost_by_chat.values()), 6), "inspector": inspector.summary()}

    add_extension_routes(app, vault, masker, off_reason)
    add_connection_routes(app, vault)
    add_document_routes(app, vault, masker, off_reason, inspector, sync=documents_sync)
    add_image_routes(app, vault, image_masker, images_off)

    if (WEB / "assets").exists():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/")
    def index():
        page = WEB / "index.html"
        return FileResponse(page) if page.exists() else {"ok": True, "hint": "UI not built: cd apps/web && npm run build"}

    return app
