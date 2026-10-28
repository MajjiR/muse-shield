"""End-to-end flow: detect -> policy -> mask -> cloud (masked) -> reconstruct."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from .cloud import CloudLLM, NetworkInspector, PrivacyViolation
from .config import Settings
from .detector import Detector, LlamaDetector
from .entities import Detection
from .llm_client import LLMError
from .masking import MaskResult, mask
from .policy import Policy, PolicyResult, evaluate, load_policy
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
        self.policy = policy or load_policy(home / "policy.json")
        self.namespace = namespace
        self.allocator = VaultAllocator(self.vault, namespace)
        self.conversations: dict[str, Conversation] = {}

    def protect(self, text: str, policy: Policy | None = None) -> Protected:
        policy = policy or self.policy
        t0 = time.perf_counter()
        detection = self.detector.detect(text, terms=policy.terms, cues=policy.cues, use_llm=policy.use_llm)
        t1 = time.perf_counter()
        result = evaluate(detection, policy)
        masked = mask(text, result, self.allocator)
        t2 = time.perf_counter()
        return Protected(detection, result, masked, {"detect": (t1 - t0) * 1000, "mask": (t2 - t1) * 1000})

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
