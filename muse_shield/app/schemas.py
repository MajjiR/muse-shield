"""Request and response models. Field names follow CONTRACT.md exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SpanOut(BaseModel):
    start: int
    end: int
    text: str
    type: str
    role: str | None = None
    placeholder: str
    kind: Literal["entity", "context"] = "entity"
    source: Literal["model", "policy", "user", "fallback"] = "model"
    fallback: str | None = None  # classify mode: the category that made this <SENSITIVE_n> private


class ContextOut(BaseModel):
    label: str
    kind: str
    subtype: str | None = None
    start: int
    end: int
    summary: str = ""


MaskMode = Literal["normal", "classify"]


class MaskRequest(BaseModel):
    text: str
    chat_id: str | None = None
    mode: MaskMode = "normal"  # classify: also detect the document's categories and their extra private details


class ImageMaskRequest(BaseModel):
    image: str  # a data: URL or bare base64 (PNG, JPEG, WebP, GIF)
    chat_id: str | None = None
    verify: bool = True  # re-scan the masked image with Muse Spark


class MaskResponse(BaseModel):
    chat_id: str
    masked_text: str
    spans: list[SpanOut] = Field(default_factory=list)
    contexts: list[ContextOut] = Field(default_factory=list)
    analysis_ok: bool = True
    error: str = ""
    latency_ms: float = 0.0
    cost_usd: float | None = None
    mask_id: str | None = None
    mode: MaskMode = "normal"
    categories: list[str] = Field(default_factory=list)
    summary: str = ""


class UnmaskRequest(BaseModel):
    text: str
    chat_id: str


class UnmaskResponse(BaseModel):
    text: str


class Ask(BaseModel):
    ask_id: str
    chat_id: str
    label: str
    kind: str
    level: Literal["shape", "summary", "full"]
    reason: str = ""
    preview: str  # exactly what would be sent to the model if allowed
    previews: dict[str, str] = Field(default_factory=dict)  # every level the user can pick, and its exact text


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None
    mask_id: str | None = None  # from a /mask preview, so Mask & send doesn't analyze twice
    document_ids: list[str] = Field(default_factory=list)  # documents to attach to this turn (message may be "")
    image_ids: list[str] = Field(default_factory=list)  # masked images (POST /images) to attach to this turn
    mode: MaskMode = "normal"  # used when there's no mask_id preview


class ChatResponse(BaseModel):
    chat_id: str
    message_id: str
    reply: str = ""  # rehydrated locally
    masked_reply: str = ""  # what the model actually wrote
    sent: list[dict] = Field(default_factory=list)  # the exact messages sent to the model
    ask: Ask | None = None
    masked: MaskResponse | None = None
    error: str = ""


class RevealRequest(BaseModel):
    ask_id: str
    decision: Literal["allow", "deny"]
    level: Literal["shape", "summary", "full"] | None = None


class VaultRevealRequest(BaseModel):
    chat_id: str
    label: str
