"""End-to-end flow: detect -> policy -> mask -> cloud (masked) -> reconstruct."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from .cloud import CloudLLM, NetworkInspector, PrivacyViolation, find_leaks
from .config import Settings
from .detector import Detector, LlamaDetector
from .entities import Detection, Entity, EntityType, Sensitivity
from .llm_client import LLMError
from .masking import MaskResult, SessionAllocator, TokenAllocator, mask
from .personalization import PolicyStore
from .policy import Policy, PolicyResult, classify, evaluate
from .reconstruct import Reconstruction, reconstruct
from .tokenizer import VaultAllocator
from .vault import Vault


@dataclass
class Protected:
    detection: Detection
    policy: PolicyResult
    masked: MaskResult
    timings_ms: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "detection": self.detection.to_dict(),
            "policy": self.policy.to_dict(),
            "masked": self.masked.to_dict(include_originals=True),
            "timings_ms": self.timings_ms,
        }


@dataclass
class Conversation:
    id: str
    masked_history: list[dict[str, str]] = field(default_factory=list)
    secrets: dict[str, str] = field(default_factory=dict)  # token -> original, in memory only


@dataclass
class AskResult:
    conversation_id: str
    protected: Protected
    cloud: str
    masked_reply: str = ""
    reconstruction: Reconstruction | None = None
    blocked: bool = False
    error: str = ""
    timings_ms: dict[str, float] = field(default_factory=dict)

    @property
    def answer(self) -> str:
        return self.reconstruction.text if self.reconstruction else ""

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "protected": self.protected.to_dict(),
            "cloud": self.cloud,
            "masked_reply": self.masked_reply,
            "reconstruction": self.reconstruction.to_dict() if self.reconstruction else None,
            "answer": self.answer,
            "blocked": self.blocked,
            "error": self.error,
            "timings_ms": self.timings_ms,
        }


class UnsupportedContent(ValueError):
    """Message content the engine cannot inspect yet (e.g. images), so it must not be sent."""


def message_text(content) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        if any(not isinstance(p, dict) or p.get("type") != "text" for p in content):
            raise UnsupportedContent("only text content parts are supported; images are not sent until on-device masking covers them")
        return "\n".join(p.get("text", "") for p in content)
    raise UnsupportedContent(f"unsupported content type: {type(content).__name__}")


@dataclass
class ChatResult:
    masked_messages: list[dict[str, str]]
    protected: list[Protected]
    masked_reply: str = ""
    reconstruction: Reconstruction | None = None
    blocked: bool = False
    error: str = ""

    @property
    def answer(self) -> str:
        return self.reconstruction.text if self.reconstruction else ""

    @property
    def tokens(self) -> list[str]:
        return sorted({t for p in self.protected for t in p.masked.mapping})


class PrivacyEngine:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        vault: Vault | None = None,
        detector: Detector | None = None,
        cloud: CloudLLM | None = None,
        inspector: NetworkInspector | None = None,
        policy: Policy | None = None,
        namespace: str = "default",
    ):
        self.settings = settings or Settings()
        home = self.settings.ensure_home()
        self.inspector = inspector or (cloud.inspector if cloud else NetworkInspector(home / "egress.jsonl"))
        self.vault = vault or Vault.open(home, self.settings.passphrase)
        self.detector = detector or Detector(LlamaDetector(self.settings.local_llm_base_url, self.settings.local_llm_model))
        self.cloud = cloud or CloudLLM(
            self.settings.cloud_base_url, self.settings.cloud_model, self.settings.cloud_api_key, inspector=self.inspector
        )
        self.store = PolicyStore(home / "policies.json")
        if policy is not None:
            self.store.active = policy
        self.namespace = namespace
        self.allocator = VaultAllocator(self.vault, namespace)
        self.conversations: dict[str, Conversation] = {}

    @property
    def policy(self) -> Policy:
        return self.store.active

    @policy.setter
    def policy(self, policy: Policy) -> None:
        self.store.active = policy

    def protect(self, text: str, policy: Policy | None = None, allocator: TokenAllocator | None = None) -> Protected:
        policy = policy or self.policy
        t0 = time.perf_counter()
        detection = self.detector.detect(text, terms=policy.terms, cues=policy.cues, use_llm=policy.use_llm)
        t1 = time.perf_counter()
        result = evaluate(detection, policy)
        masked = mask(text, result, allocator or self.allocator)
        t2 = time.perf_counter()
        return Protected(detection, result, masked, {"detect": (t1 - t0) * 1000, "mask": (t2 - t1) * 1000})

    def dry_run(self, text: str, policy: Policy) -> MaskResult:
        """Mask with a throwaway allocator: for tests and benchmarks, never touches the vault."""
        return self.protect(text, policy, SessionAllocator()).masked

    def conversation(self, conversation_id: str | None) -> Conversation:
        cid = conversation_id or uuid.uuid4().hex[:10]
        return self.conversations.setdefault(cid, Conversation(cid))

    def ask(self, text: str, conversation_id: str | None = None) -> AskResult:
        conv = self.conversation(conversation_id)
        protected = self.protect(text)
        result = AskResult(conv.id, protected, self.cloud.name, timings_ms=dict(protected.timings_ms))

        if protected.masked.blocked:
            kinds = sorted({d.entity.type.value for d in protected.masked.blocked})
            result.blocked = True
            result.error = f"blocked by policy: message contains {', '.join(kinds)}"
            return result

        secrets = {**conv.secrets, **protected.masked.mapping}
        messages = [*conv.masked_history, {"role": "user", "content": protected.masked.masked}]
        t0 = time.perf_counter()
        try:
            result.masked_reply = self.cloud.complete(messages, secrets, conv.id)
        except PrivacyViolation as exc:
            result.blocked, result.error = True, str(exc)
            return result
        except LLMError as exc:
            result.error = f"cloud error: {exc}"
            return result
        t1 = time.perf_counter()
        result.reconstruction = reconstruct(result.masked_reply, secrets, self.allocator.reveal)
        result.timings_ms["cloud"] = (t1 - t0) * 1000
        result.timings_ms["reconstruct"] = (time.perf_counter() - t1) * 1000

        conv.secrets = secrets
        conv.masked_history += [
            {"role": "user", "content": protected.masked.masked},
            {"role": "assistant", "content": result.masked_reply},
        ]
        return result

    def chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> ChatResult:
        """Stateless OpenAI-style chat: mask every message, ask the cloud, restore the reply.

        Clients resend the full history on every call. Vault tokens are
        consistent, so PERSON_1 stays the same person across turns without
        any server-side conversation state.
        """
        masked_messages, protected, secrets = [], [], {}
        for m in messages:
            p = self.protect(message_text(m.get("content")))
            protected.append(p)
            secrets.update(p.masked.mapping)
            masked_messages.append({"role": m.get("role", "user"), "content": p.masked.masked})
        result = ChatResult(masked_messages, protected)

        blocked = sorted({d.entity.type.value for p in protected for d in p.masked.blocked})
        if blocked:
            result.blocked, result.error = True, f"blocked by policy: message contains {', '.join(blocked)}"
            return result
        try:
            result.masked_reply = self.cloud.complete(masked_messages, secrets, "proxy", temperature, max_tokens)
        except PrivacyViolation as exc:
            result.blocked, result.error = True, str(exc)
            return result
        except LLMError as exc:
            result.error = f"cloud error: {exc}"
            return result
        result.reconstruction = reconstruct(result.masked_reply, secrets, self.allocator.reveal)
        return result

    # -- proof that raw values never left -----------------------------------
    def audit(self) -> dict:
        """Decrypt every vault value locally and scan every recorded egress body for it.

        A value that is public on its own (e.g. "Meta", masked once inside an
        acquisition memo) may legitimately appear in a later, ordinary question.
        Those are reported separately as public_in_context, not as leaks.
        """
        secrets, context_public = {}, set()
        for e in self.vault.entries(self.namespace):
            value = self.allocator.reveal(e.token) or ""
            secrets[e.token] = value
            entity = Entity(value, EntityType(e.kind), 0, len(value))
            if classify(entity, self.policy, confidential_context=False)[0] is Sensitivity.PUBLIC:
                context_public.add(e.token)

        records = list(self.inspector.records)
        leaks, public_hits = [], []
        for rec in records:
            found = find_leaks(rec.request_body, secrets)
            hard = [t for t in found if t not in context_public]
            if hard:
                leaks.append({"record": rec.id, "tokens": hard})
            if len(hard) < len(found):
                public_hits.append({"record": rec.id, "tokens": [t for t in found if t in context_public]})
        return {
            "requests_scanned": len(records),
            "bytes_scanned": sum(r.request_bytes for r in records),
            "secrets_checked": len(secrets),
            "comparisons": len(records) * len(secrets),
            "leaks": leaks,
            "public_in_context": public_hits,
            "clean": not leaks,
        }

    def attempt_raw_send(self, text: str) -> dict:
        """Demo: bypass masking and try to send raw text. The egress guard must refuse."""
        mapping = self.protect(text, allocator=SessionAllocator()).masked.mapping
        before = len(self.inspector.records)
        try:
            self.cloud.complete([{"role": "user", "content": text}], mapping)
        except PrivacyViolation as exc:
            return {"sent": False, "refused": str(exc), "requests_added": len(self.inspector.records) - before}
        return {"sent": True, "refused": "", "requests_added": len(self.inspector.records) - before}
