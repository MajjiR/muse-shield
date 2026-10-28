# Privacy Engine

**Use frontier cloud LLMs without your raw data ever leaving the device.**

A small Llama (~1B) runs locally and finds PII and confidential context in your prompt.
It replaces those values with semantic tokens: `Sarah Chen` → `PERSON_1`, `$1.2B` →
`MAJOR_TRANSACTION_VALUE`. The cloud model only ever sees the masked prompt. Its answer
comes back with tokens, which are restored on your machine from an encrypted vault.

```
 you ──▶ local detector ──▶ policy ──▶ semantic mask ──▶ egress guard ──▶ cloud LLM
         (Llama 1B + rules)  (PII /     (encrypted vault,  (refuses raw     (sees tokens
                              confidential / consistent     values)          only)
                              public)        tokens)                            │
 you ◀── local reconstruction ◀──────────────────────────── masked answer ◀────┘
```

Built for the Meta × Cerebral Valley AI hackathon.

## Why semantic masking, not redaction

Redaction (`[REDACTED]`) protects data but makes the model useless: it can't tell two
people apart or know whether a deal is big. Semantic tokens keep the *role* and the
*magnitude* and drop the identity. From `privacy-engine bench` (160 synthetic prompts, rules-only detector):

| strategy | leak ↓ | over-mask ↓ | distinct ↑ | magnitude ↑ | context ↑ | restorable ↑ | utility ↑ |
|---|---|---|---|---|---|---|---|
| raw | 100% | 0% | 100% | 100% | 100% | 100% | 100% |
| redact | 18% | 0% | 7% | 0% | 100% | 26% | 36% |
| pii-only | 72% | 0% | 100% | 100% | 100% | 100% | 100% |
| **semantic** | **18%** | 0% | 100% | 100% | 100% | 100% | **100%** |
| **semantic+taught** | **6%** | 0% | 100% | 100% | 100% | 100% | **100%** |
| strict | 18% | 67% | 100% | 100% | 25% | 100% | 75% |

Semantic masking leaks no more than redaction and keeps all of the model-free utility.
The remaining leaks are names, orgs and codenames that are deliberately outside the rule
lexicons. Teaching your own vocabulary cuts them by two thirds. The local Llama detector
(`--llm`) and the LoRA adapter (`docs/LORA.md`) target what's left.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/privacy-engine demo      # scripted run + leak audit, no network needed
.venv/bin/privacy-engine serve     # dashboard at http://127.0.0.1:8787
```

Optional local Llama detector:

```bash
brew install ollama
ollama serve
ollama pull llama3.2:1b
```

Real cloud model: set `MODEL_API_KEY` in `.env` to use **Muse Spark** (`muse-spark-1.3`) on the
Meta Model API. Any OpenAI-compatible endpoint works via `CLOUD_BASE_URL` / `CLOUD_MODEL`. Without Ollama the
detector uses rules only. Without a key, an offline mock cloud answers in tokens.

## Drop-in proxy: privacy for any app in one line

The server speaks the OpenAI Chat Completions protocol at `/v1`. Point any existing
OpenAI-SDK app or agent at it, and every request gets on-device masking, then Muse Spark,
then local reconstruction:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8787/v1", api_key="unused")  # the only change
client.chat.completions.create(model="muse-spark-1.3", messages=[...])
```

- **Stateless.** Clients resend history, and consistent vault tokens keep `PERSON_1` the same
  person across turns.
- **Streaming works.** The answer is restored first, then sent as one chunk.
- **Keys and model.** The client's API key is ignored and never forwarded. The configured
  cloud model is always used.
- **What gets refused.** Policy-blocked messages and image parts get an HTTP 400 and nothing
  is sent.

## 3-minute demo script

1. **Chat**: send the first example. Pane 1 shows on-device detections, pane 2 shows the
   only text that left the device, and pane 3 shows the answer restored locally.
2. Send *"What did Meta announce at Connect?"*. It goes through unmasked because it's public.
   Then send the *"Confidential: we're acquiring Meta's AR unit"* example. Now Meta is masked,
   because sensitivity depends on context.
3. **Personalize**: teach `Bluebird` as a PROJECT, run tests (`1 fixed, 0 regressed`), deploy.
   It is masked from then on.
4. **Network inspector**: open a request to see the exact bytes sent. Click *Run leak audit*.
   It decrypts every vault value locally and searches all traffic: 0 leaks. Click *Attempt raw
   send* and the egress guard refuses before a request is made.
5. **Vault**: tokens are AES-256-GCM encrypted at rest. Click reveal to decrypt one locally.

## How it holds up

- **Detection.** Regexes with checksums (Luhn) catch structured IDs, lexicons catch names and
  orgs, and a local Llama 1B adds free-form entities and a confidential-context signal. LLM
  spans are re-grounded in the input, so the model can't hallucinate a span.
- **Policy.** Each entity is classified as PII, CONFIDENTIAL or PUBLIC, then masked, blocked or
  allowed. Public companies and small amounts escalate in confidential context, and money ≥ $1M
  is always confidential.
- **Consistent tokens.** "Sarah Chen", "Ms. Chen" and "Sarah" map to the same `PERSON_1`.
  "$1.2B" and "$1,200,000,000" map to the same token. This holds across conversations.
  Ambiguous first names get a new token instead of being merged with the wrong person.
- **Vault.** SQLite with AES-256-GCM, with the token bound as associated data so tampered rows
  fail. HMAC lookups mean no plaintext is stored. The key comes from scrypt or a random 0600 file.
- **Egress.** The serialized payload is scanned for every original value, including
  JSON-escaped and reformatted numbers, before sending. The bytes actually sent are captured by
  httpx hooks and re-scanned.
- **Reconstruction.** Tolerates model drift (`[PERSON_1]`, `person_1`, `**PERSON_1**`) and flags
  tokens the model invented.

## CLI

```bash
privacy-engine serve | demo | protect "…" | ask "…" | bench [--llm] [--online K] | lora-data
```

## Layout

| Path | What |
| --- | --- |
| `privacy_engine/detector/` | rules (regex, Luhn, lexicons) + local Llama 1B detector, merged |
| `privacy_engine/policy.py` | PII / CONFIDENTIAL / PUBLIC classification, context escalation, mask/block/allow |
| `privacy_engine/masking.py` | semantic tokens (`PERSON_1`, `MAJOR_TRANSACTION_VALUE`) with magnitude buckets |
| `privacy_engine/vault.py` | AES-256-GCM SQLite vault, HMAC lookups, scrypt or 0600 key file |
| `privacy_engine/tokenizer.py` | consistent tokens across spellings and conversations |
| `privacy_engine/cloud.py` | cloud gateway: egress guard, wire-level network inspector, offline mock cloud |
| `privacy_engine/reconstruct.py` | on-device token → value restore, tolerant of model drift |
| `privacy_engine/pipeline.py` | `PrivacyEngine.ask()`: detect → mask → cloud → restore, multi-turn, leak audit |
| `privacy_engine/personalization.py` | Teach → Test → Deploy: draft policy, regression suite, versioned deploy + rollback |
| `privacy_engine/bench.py` | privacy vs utility benchmark on seeded synthetic data |
| `privacy_engine/lora.py`, `scripts/lora_*.py`, `docs/LORA.md` | LoRA data from Teach, train/eval on MPS, deploy via Ollama ADAPTER |
| `privacy_engine/server.py`, `web/index.html` | local dashboard (127.0.0.1 only) |
| `privacy_engine/cli.py` | command line |
| `tests/` | 54 tests; no network or model needed |

## Known limits

- The rules-only detector misses names and codenames outside its lexicons (see the benchmark).
  Run Ollama, teach your terms, or train the LoRA adapter.
- The mock cloud is a template, not a model. Utility numbers in the table are model-free
  proxies. `bench --online K` scores real answers on synthetic data.
- The LoRA train and eval scripts have not been run yet (they need torch and the gated model).
- Token numbering persists per namespace, so a cloud provider could link `PERSON_1` across
  conversations. Use separate namespaces if that matters.
