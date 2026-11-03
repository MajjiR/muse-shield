"""Model backends that implement analyze(). All speak the OpenAI Chat Completions protocol.

    GlimmerBackend    Muse Glimmer 30B. Fireworks serverless by default; point
                      GLIMMER_BASE_URL at a vLLM/SGLang server to self-host.
    MetaModelBackend  Any Meta Model API model (muse-spark-1.3, muse-wonder-1.0).
                      Analysis sees raw text, so it refuses to run unless
                      META_SYNTHETIC_ONLY=1: synthetic or public benchmark data only.

ENGINE_BACKEND=glimmer | muse_spark | muse_wonder selects one via backend_from_env().
"""

from __future__ import annotations

import json
import os
import time

import httpx

from .analysis import AMOUNT_ROLES, CONTEXT_KINDS, ENTITY_TYPES, Analysis, ContractError, number_sentences, parse, split_sentences
from .config import load_env

SYSTEM_PROMPT = f"""You find private and confidential information in text for a privacy gateway.
The input is one paragraph with numbered sentences, plus labels of contexts already known in this chat.
Return ONE JSON object and nothing else:
{{"entities": [{{"text": "...", "type": "...", "role": "..."}}],
  "contexts": [{{"sentences": [1], "kind": "...", "subtype": "...", "refers_to": null, "summary": "..."}}]}}

entities: every span that identifies or describes a person or business.
- type is one of {sorted(ENTITY_TYPES)}:
  PERSON names · ORG companies and institutions · ADDRESS street addresses · LOCATION cities, regions, countries
  AMOUNT money · PROJECT internal codenames · ID account, customer, employee, medical, tax or government numbers
  CONTACT phone numbers, emails, URLs, usernames · DATE dates and times tied to a person (birth dates, appointments)
  SECRET passwords, PINs, CVVs, API keys · SENSITIVE_ATTRIBUTE health, religion, ethnicity, sexuality,
  political views, gender, age, occupation and other personal attributes
- AMOUNT needs a role, one of {sorted(AMOUNT_ROLES)}.
- Copy `text` EXACTLY as it appears, character for character. Never invent text. Never output offsets.
contexts: sentences that describe a deal, decision, plan, negotiation, project or HR matter.
- kind is one of {sorted(CONTEXT_KINDS)}. subtype is a short UPPER_CASE word (e.g. PURCHASE, HIRING).
- refers_to is a known context label this continues, else null. summary is under 8 words, with no names or numbers.
If nothing is sensitive return {{"entities": [], "contexts": []}}."""

EXAMPLE_USER = 'Known contexts: none\n[1] Priya Shah earns 18 lakh rupees at Northwind. [2] We will acquire Kestrel next quarter.'
EXAMPLE_ASSISTANT = json.dumps({
    "entities": [
        {"text": "Priya Shah", "type": "PERSON"},
        {"text": "18 lakh rupees", "type": "AMOUNT", "role": "SALARY"},
        {"text": "Northwind", "type": "ORG"},
        {"text": "Kestrel", "type": "ORG"},
    ],
    "contexts": [{"sentences": [2], "kind": "DEAL", "subtype": "ACQUISITION", "refers_to": None,
                  "summary": "plans to acquire a company"}],
})


class BackendError(RuntimeError):
    pass


class Backend:
    name = "backend"

    def analyze(self, paragraphs: list[str], known_labels: list[str] | None = None) -> list[Analysis]:
        raise NotImplementedError


class ChatBackend(Backend):
    """Shared implementation: one chat call per paragraph, one retry on contract violations."""

    def __init__(self, base_url: str, model: str, api_key: str, *, client: httpx.Client | None = None,
                 timeout: float = 60.0, max_tokens: int = 1024, retries: int = 1):
        if not api_key:
            raise BackendError(f"{self.name}: missing API key")
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.timeout, self.max_tokens, self.retries = timeout, max_tokens, retries
        self.json_mode = True  # turned off once if the server rejects response_format
        self._client = client or httpx.Client()

    def _post(self, messages: list[dict]) -> httpx.Response:
        payload = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens}
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return self._client.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout,
                                 headers={"Authorization": f"Bearer {self.api_key}"})

    def _call(self, messages: list[dict]) -> tuple[str, dict]:
        try:
            for attempt in range(4):
                r = self._post(messages)
                if r.status_code in (400, 422) and self.json_mode and "response_format" in r.text:
                    self.json_mode = False  # this server doesn't take JSON mode; the prompt still asks for JSON
                    continue
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
                    continue
                break
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"] or "", data.get("usage") or {}
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"{self.name}: {exc}") from exc

    def analyze_one(self, paragraph: str, known_labels: list[str] | None = None) -> Analysis:
        sentences = split_sentences(paragraph) or [paragraph]
        known = ", ".join(known_labels or []) or "none"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": EXAMPLE_USER},
            {"role": "assistant", "content": EXAMPLE_ASSISTANT},
            {"role": "user", "content": f"Known contexts: {known}\n{number_sentences(sentences)}"},
        ]
        usage: dict = {}
        t0 = time.perf_counter()
        error = ""
        for attempt in range(1, self.retries + 2):
            raw, u = self._call(messages)
            for k, v in u.items():
                if isinstance(v, int):
                    usage[k] = usage.get(k, 0) + v
            try:
                result = parse(raw, paragraph, sentences)
                result.attempts, result.usage = attempt, usage
                result.latency_ms = (time.perf_counter() - t0) * 1000
                return result
            except ContractError as exc:
                error = str(exc)
                messages += [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That output broke the contract ({error}). Reply with only the corrected JSON object."},
                ]
        return Analysis(paragraph, sentences, valid=False, attempts=self.retries + 1, error=error,
                        latency_ms=(time.perf_counter() - t0) * 1000, usage=usage)

    def analyze(self, paragraphs: list[str], known_labels: list[str] | None = None) -> list[Analysis]:
        return [self.analyze_one(p, known_labels) for p in paragraphs]


class GlimmerBackend(ChatBackend):
    name = "glimmer"


class MetaModelBackend(ChatBackend):
    """A Meta Model API model. Raw text reaches Meta, so only synthetic or public data is allowed."""

    def __init__(self, *args, name: str = "meta", synthetic_only: bool = False, **kwargs):
        self.name = name
        if not synthetic_only:
            raise BackendError(f"{name} analysis sends raw text to the Meta Model API: "
                               "only allowed on synthetic or public data (META_SYNTHETIC_ONLY=1)")
        super().__init__(*args, **kwargs)


MuseSparkBackend = MetaModelBackend  # backwards-compatible name

META_MODELS = {"muse_spark": ("CLOUD_MODEL", "muse-spark-1.3"), "muse_wonder": ("MUSE_WONDER_MODEL", "muse-wonder-1.0")}


def backend_from_env(name: str | None = None, client: httpx.Client | None = None) -> Backend:
    load_env()
    name = name or os.environ.get("ENGINE_BACKEND", "glimmer")
    if name == "glimmer":
        return GlimmerBackend(
            os.environ.get("GLIMMER_BASE_URL", "https://api.fireworks.ai/inference/v1"),
            os.environ.get("GLIMMER_MODEL", "accounts/fireworks/models/muse-glimmer-30b"),
            os.environ.get("GLIMMER_API_KEY") or os.environ.get("FIREWORKS_API_KEY", ""),
            client=client,
        )
    if name in META_MODELS:
        env_var, default = META_MODELS[name]
        synthetic = "1" in (os.environ.get("META_SYNTHETIC_ONLY"), os.environ.get("MUSE_SPARK_SYNTHETIC_ONLY"))
        return MetaModelBackend(
            os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"),
            os.environ.get(env_var, default),
            os.environ.get("MODEL_API_KEY", ""),
            name=name, synthetic_only=synthetic, client=client,
        )
    raise BackendError(f"unknown ENGINE_BACKEND {name!r} (expected glimmer, muse_spark or muse_wonder)")
