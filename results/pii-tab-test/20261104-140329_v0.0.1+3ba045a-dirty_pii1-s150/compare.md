# Nemotron-PII benchmark · 30 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-sampler `rohan-majji/run-3ae33b189bfd44bbb59217963a11fcfe/step-150-008d387b` | 17.6% | 17.6% | 86.2% | 77.6% | 93.1% | 100.0% | 100.0% | 1 | 110.1s / 116.0s | 295,556/20,328 | – |

## Recall by type

| type | glimmer-sampler |
|---|---|
| OTHER | 86.2% |

## Recall by label

| label | n | glimmer-sampler |
|---|---|---|
| DATE | 556 | 94.4% |
| ID | 72 | 98.6% |
| LOCATION | 34 | 94.1% |
| ORG | 118 | 52.5% |
| PERSON | 182 | 76.4% |
