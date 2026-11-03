# Muse Shield

**A privacy gateway between people and Meta's Muse models.**

Before a message, image or document reaches the model, Muse Shield replaces sensitive
information with consistent placeholders (`PERSON_1`, `SALARY_1`, `DEAL_1`). Only the masked
version is sent. The real values are put back into the reply on the user's machine, so the
model provider never sees real data.

Built for the Meta Global AI Developer Hackathon (Cerebral Valley).

## Status

The core is being rebuilt in `muse_shield/` against the final design. The working first
prototype is kept, still runnable, in [`prototyping/`](prototyping/). It has 59 tests and
covers detection, policy, semantic masking, an encrypted vault, consistent tokens, a
masked-only cloud gateway, local reconstruction, a dashboard, a network inspector, and an
OpenAI-compatible proxy.

## Muse Glimmer analysis and evals

`muse_shield.backends` sends one paragraph per call to Muse Glimmer 30B and expects one JSON
object back, with `entities` (text, type, role for amounts) and `contexts` (sentence numbers,
kind). The model never returns character offsets. Code finds each entity by exact search and
drops any it can't find. Invalid JSON gets one retry.

```bash
cp .env.example .env          # add FIREWORKS_API_KEY
.venv/bin/python -m muse_shield.evals --backend glimmer --n 60
```

The eval set is synthetic: fake names and Indian addresses and amounts, with 10 templates
including the acceptance case. It reports:
- JSON validity, first try and after the retry
- entity precision, recall and F1, overall and by type
- amount-role accuracy
- context detection and kind accuracy
- hallucinated spans
- latency and cost

## Develop

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Run the prototype:

```bash
.venv/bin/pip install -e 'prototyping[dev]'
cd prototyping && ../.venv/bin/pytest && ../.venv/bin/privacy-engine serve
```
