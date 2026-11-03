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
    source: Literal["model", "policy", "user"] = "model"


class ContextOut(BaseModel):
    label: str
    kind: str
    subtype: str | None = None
    start: int
    end: int
    summary: str = ""


class MaskRequest(BaseModel):
    text: str
    chat_id: str | None = None


class MaskResponse(BaseModel):
    chat_id: str
    masked_text: str
    spans: list[SpanOut] = Field(default_factory=list)
    contexts: list[ContextOut] = Field(default_factory=list)
    analysis_ok: bool = True
    error: str = ""
    latency_ms: float = 0.0
    cost_usd: float | None = None


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


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None


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
