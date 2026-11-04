# Nemotron-PII benchmark · 100 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-sampler `rohan-majji/run-3ae33b189bfd44bbb59217963a11fcfe/step-150-008d387b` | 16.3% | 16.3% | 82.8% | 71.4% | 97.7% | 100.0% | 100.0% | 7 | 19.2s / 42.0s | 551,977/21,360 | – |

## Recall by type

| type | glimmer-sampler |
|---|---|
| OTHER | 82.8% |

## Recall by label

| label | n | glimmer-sampler |
|---|---|---|
| ADDRESS | 95 | 94.7% |
| CONTACT | 52 | 94.2% |
| DATE | 173 | 80.3% |
| ID | 55 | 63.6% |
| LOCATION | 4 | 100.0% |
| ORG | 90 | 75.6% |
| PERSON | 155 | 83.9% |
| SECRET | 8 | 100.0% |
