# Privacy Engine

**Use frontier cloud LLMs without your raw data ever leaving the device.**

A small Llama (~1B) runs locally, finds PII and confidential context in your prompt,
and replaces it with semantic tokens (`Sarah Chen` → `PERSON_1`, `$1.2B` →
`MAJOR_TRANSACTION_VALUE`). Only the masked prompt goes to the cloud model. The
answer comes back with tokens, and is reconstructed locally from an encrypted vault.

```
 you ──▶ local detector ──▶ policy ──▶ semantic mask ──▶ cloud LLM
         (Llama 1B + rules)  (PII /     (vault, AES-GCM)   (sees tokens only)
                              confidential /                     │
                              public)                            ▼
 you ◀── local reconstruction ◀───────────── masked answer ◀─────┘
```

Built for the Meta × Cerebral Valley AI hackathon.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env
# optional, for the local Llama detector:
brew install ollama && ollama serve & ollama pull llama3.2:1b
```

```bash
.venv/bin/privacy-engine serve          # dashboard at http://127.0.0.1:8787
.venv/bin/privacy-engine protect "Email Sarah Chen about the $1.2B deal"
```

Without Ollama the detector falls back to rules only; without `CLOUD_API_KEY` the
cloud call goes to an offline mock, so the whole demo runs on a laptop with no network.

## Layout

| Path | What |
| --- | --- |
| `privacy_engine/config.py` | settings from env / `.env` |
| `privacy_engine/detector/` | rules (regex, Luhn, lexicons) + local Llama 1B detector, merged |
| `privacy_engine/policy.py` | PII / CONFIDENTIAL / PUBLIC classification, context escalation, mask/block/allow |
| `privacy_engine/masking.py` | semantic tokens (`PERSON_1`, `MAJOR_TRANSACTION_VALUE`) with magnitude buckets |
| `privacy_engine/vault.py` | AES-256-GCM SQLite vault, HMAC lookups, scrypt or 0600 key file |
| `privacy_engine/tokenizer.py` | consistent tokens across spellings and conversations (aliases, normalization) |
| `privacy_engine/cloud.py` | cloud gateway: egress guard, wire-level network inspector, offline mock cloud |
| `privacy_engine/reconstruct.py` | on-device token -> value restore, tolerant of model drift |
| `privacy_engine/pipeline.py` | `PrivacyEngine.ask()`: the full detect -> mask -> cloud -> restore loop, multi-turn |
| `privacy_engine/server.py`, `web/index.html` | local dashboard (127.0.0.1 only): chat panes, policy editor, vault |
| `privacy_engine/personalization.py` | Teach -> Test -> Deploy: draft policy, regression suite, versioned deploy + rollback |
| `privacy_engine/cli.py` | `privacy-engine serve \| protect \| ask` |
