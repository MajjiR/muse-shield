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

Without Ollama the detector falls back to rules only; without `CLOUD_API_KEY` the
cloud call goes to an offline mock, so the whole demo runs on a laptop with no network.

## Layout

| Path | What |
| --- | --- |
| `privacy_engine/config.py` | settings from env / `.env` |
