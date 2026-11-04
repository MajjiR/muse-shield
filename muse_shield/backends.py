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
  SECRET passwords, PINs, CVVs, API keys · SENSITIVE_ATTRIBUTE health conditions, religion, ethnicity, sexuality,
  political views, criminal record, pregnancy and other special-category facts about a person
- Not entities: job titles and roles (CTO, engineer, nurse, Advocate), weekdays and relative dates (Friday, tomorrow,
  next quarter), generic nouns, and well-known public bodies (CERT-In, RBI). Leave them readable.
- AMOUNT needs a role, one of {sorted(AMOUNT_ROLES)}.
- Copy `text` EXACTLY as it appears, character for character. Never invent text. Never output offsets.
contexts: sentences that state facts about a deal, decision, plan, negotiation, project or HR matter.
- Never mark the user's own request, question or instruction to the assistant as a context
  ("Draft an email to ...", "Summarize ...", "Is this a good offer?"). Mask only the entities inside it.
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


# Stage-1 "PII only" task: the same entity rules, but no contexts. A separate prompt keeps the stage-1
# model from learning "contexts are always empty" under the full prompt, which stage 2 trains later.
PII_SYSTEM_PROMPT = SYSTEM_PROMPT.split("\ncontexts:", 1)[0].replace(
    "The input is one paragraph with numbered sentences, plus labels of contexts already known in this chat.",
    "The input is one paragraph with numbered sentences.").replace(
    """{{"entities": [{{"text": "...", "type": "...", "role": "..."}}],
  "contexts": [{{"sentences": [1], "kind": "...", "subtype": "...", "refers_to": null, "summary": "..."}}]}}""".replace("{{", "{").replace("}}", "}"),
    '{"entities": [{"text": "...", "type": "...", "role": "..."}]}').replace(
    "DATE dates and times tied to a person (birth dates, appointments)", "DATE specific calendar dates and clock times").replace(
    "SENSITIVE_ATTRIBUTE health conditions, religion,", "SENSITIVE_ATTRIBUTE health conditions, blood type, age, gender, religion,"
) + '\nIf nothing is sensitive return {"entities": []}.'
PII_EXAMPLE_USER = EXAMPLE_USER.split("\n", 1)[1]
PII_EXAMPLE_ASSISTANT = json.dumps({"entities": json.loads(EXAMPLE_ASSISTANT)["entities"]})


def task_messages(task: str, sentences: list[str], known: str = "none") -> list[dict]:
    """The exact message layout for a task ("full" or "pii"); training rows use the same function."""
    if task == "pii":
        return [{"role": "system", "content": PII_SYSTEM_PROMPT}, {"role": "user", "content": PII_EXAMPLE_USER},
                {"role": "assistant", "content": PII_EXAMPLE_ASSISTANT}, {"role": "user", "content": number_sentences(sentences)}]
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": EXAMPLE_USER},
            {"role": "assistant", "content": EXAMPLE_ASSISTANT},
            {"role": "user", "content": f"Known contexts: {known}\n{number_sentences(sentences)}"}]


class BackendError(RuntimeError):
    pass


class Backend:
    name = "backend"

    def analyze(self, paragraphs: list[str], known_labels: list[str] | None = None) -> list[Analysis]:
        raise NotImplementedError


class ChatBackend(Backend):
    """Shared implementation: one chat call per paragraph, one retry on contract violations."""

    task = "full"  # "pii": the stage-1 entities-only prompt (ANALYSIS_TASK=pii)

    def __init__(self, base_url: str, model: str, api_key: str, *, client: httpx.Client | None = None,
                 timeout: float = 60.0, max_tokens: int = 1024, retries: int = 1, extra: dict | None = None):
        if not api_key:
            raise BackendError(f"{self.name}: missing API key")
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.timeout, self.max_tokens, self.retries = timeout, max_tokens, retries
        self.json_mode = True  # turned off once if the server rejects response_format
        self.extra = extra or {}  # provider-specific request fields, e.g. reasoning_effort
        self.scale_up_wait = 900  # seconds to wait for a scaled-to-zero deployment to come back
        self._client = client or httpx.Client()

    def _post(self, messages: list[dict]) -> httpx.Response:
        payload = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens, **self.extra}
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return self._client.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout,
                                 headers={"Authorization": f"Bearer {self.api_key}"})

    def _call(self, messages: list[dict]) -> tuple[str, dict]:
        try:
            attempt = waited = 0
            transport_errors = 0
            while True:
                try:
                    r = self._post(messages)
                except httpx.TransportError:  # timeouts, dropped connections: transient under load
                    transport_errors += 1
                    if transport_errors > 3:
                        raise
                    time.sleep(5 * transport_errors)
                    continue
                if r.status_code in (400, 422) and self.json_mode and "response_format" in r.text:
                    self.json_mode = False  # this server doesn't take JSON mode; the prompt still asks for JSON
                    continue
                if r.status_code == 503 and "SCALING_UP" in r.text and waited < self.scale_up_wait:
                    # A scale-to-zero deployment is booting a GPU: requests aren't queued, so wait it out.
                    time.sleep(15)
                    waited += 15
                    continue
                if r.status_code == 429 and attempt < 10:
                    # Rate limits are per team (Contributor: 150 RPM), so back off patiently instead of failing.
                    time.sleep(float(r.headers.get("retry-after") or min(2 ** attempt, 30)))
                    attempt += 1
                    continue
                if r.status_code in (500, 502, 503, 504) and attempt < 3:
                    time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
                    attempt += 1
                    continue
                break
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"] or "", data.get("usage") or {}
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"{self.name}: {exc}") from exc

    def analyze_one(self, paragraph: str, known_labels: list[str] | None = None) -> Analysis:
        sentences = split_sentences(paragraph) or [paragraph]
        messages = task_messages(self.task, sentences, ", ".join(known_labels or []) or "none")
        usage: dict = {}
        t0 = time.perf_counter()
        error = ""
        for attempt in range(1, self.retries + 2):
            raw, u = self._call(messages)
            for k, v in u.items():
                if isinstance(v, int):
                    usage[k] = usage.get(k, 0) + v
                elif isinstance(v, dict):  # e.g. prompt_tokens_details.cached_tokens, completion_tokens_details.reasoning_tokens
                    for kk, vv in v.items():
                        if isinstance(vv, int):
                            usage[f"{k}.{kk}"] = usage.get(f"{k}.{kk}", 0) + vv
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
    """A Meta Model API model. Raw text reaches Meta, so only synthetic or public data is allowed.

    Muse Spark and Muse Wonder are reasoning models: hidden reasoning tokens count against
    max_tokens, and at 1,024 they used it all and returned empty content. So these get a
    larger budget and an explicit reasoning_effort.
    """

    def __init__(self, *args, name: str = "meta", synthetic_only: bool = False, reasoning_effort: str = "low",
                 max_tokens: int = 4096, **kwargs):
        self.name = name
        if not synthetic_only:
            raise BackendError(f"{name} analysis sends raw text to the Meta Model API: "
                               "only allowed on synthetic or public data (META_SYNTHETIC_ONLY=1)")
        extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
        super().__init__(*args, max_tokens=max_tokens, extra=extra, timeout=kwargs.pop("timeout", 180.0), **kwargs)


MuseSparkBackend = MetaModelBackend  # backwards-compatible name


class AzureFoundryBackend(ChatBackend):
    """A model deployed in Azure AI Foundry (e.g. DeepSeek-V4-Pro), via its OpenAI-compatible v1 API.

    For building and checking training data only (synthetic or public text): never real user data,
    never at runtime. `model` is the Foundry deployment name; AZURE_OPENAI_ENDPOINT is the resource
    endpoint, AZURE_OPENAI_API_KEY its key.
    """

    def __init__(self, deployment: str, *, endpoint: str | None = None, api_key: str | None = None, max_tokens: int = 8192, **kwargs):
        load_env()
        self.name = f"azure-{deployment}"
        endpoint = (endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
        if not endpoint:
            raise BackendError("AZURE_OPENAI_ENDPOINT is not set")
        base = endpoint if endpoint.endswith("/openai/v1") else f"{endpoint}/openai/v1"
        super().__init__(base, deployment, api_key or os.environ.get("AZURE_OPENAI_API_KEY", ""), max_tokens=max_tokens,
                         timeout=kwargs.pop("timeout", 240.0), **kwargs)

    def _post(self, messages: list[dict]) -> httpx.Response:
        payload = {"model": self.model, "messages": messages, "temperature": 0, "max_tokens": self.max_tokens, **self.extra}
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return self._client.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout,
                                 headers={"api-key": self.api_key})

META_MODELS = {"muse_spark": ("CLOUD_MODEL", "muse-spark-1.3"), "muse_wonder": ("MUSE_WONDER_MODEL", "muse-wonder-1.0")}


def backend_from_env(name: str | None = None, client: httpx.Client | None = None) -> Backend:
    load_env()
    name = name or os.environ.get("ENGINE_BACKEND", "glimmer")
    if name == "glimmer":
        # Glimmer is not serverless on Fireworks: it runs on an on-demand deployment, addressed as
        # "<model>#<deployment>". GLIMMER_DEPLOYMENT=accounts/<you>/deployments/<id> fills that in.
        model = os.environ.get("GLIMMER_MODEL", "accounts/fireworks/models/muse-glimmer-30b")
        deployment = os.environ.get("GLIMMER_DEPLOYMENT", "")
        if deployment and "#" not in model:
            model = f"{model}#{deployment}"
        b = GlimmerBackend(
            os.environ.get("GLIMMER_BASE_URL", "https://api.fireworks.ai/inference/v1"),
            model,
            os.environ.get("GLIMMER_API_KEY") or os.environ.get("FIREWORKS_API_KEY", ""),
            client=client,
        )
        b.task = os.environ.get("ANALYSIS_TASK", "full")
        return b
    if name in META_MODELS:
        env_var, default = META_MODELS[name]
        synthetic = "1" in (os.environ.get("META_SYNTHETIC_ONLY"), os.environ.get("MUSE_SPARK_SYNTHETIC_ONLY"))
        return MetaModelBackend(
            os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"),
            os.environ.get(env_var, default),
            os.environ.get("MODEL_API_KEY", ""),
            name=name, synthetic_only=synthetic, client=client,
            reasoning_effort=os.environ.get("META_REASONING_EFFORT", "low"),
            max_tokens=int(os.environ.get("META_MAX_TOKENS", "4096")),
        )
    raise BackendError(f"unknown ENGINE_BACKEND {name!r} (expected glimmer, muse_spark or muse_wonder)")
