# Nemotron-PII benchmark · 200 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-sampler `rohan-majji/run-3ae33b189bfd44bbb59217963a11fcfe/step-150-008d387b` | 0.9% | 0.9% | 99.4% | 96.8% | 99.1% | 100.0% | 100.0% | 1 | 6.6s / 17.5s | 137,129/16,370 | – |

## Recall by type

| type | glimmer-sampler |
|---|---|
| OTHER | 99.4% |

## Recall by label

| label | n | glimmer-sampler |
|---|---|---|
| ADDRESS | 71 | 100.0% |
| CONTACT | 103 | 99.0% |
| DATE | 187 | 99.5% |
| ID | 355 | 100.0% |
| LOCATION | 18 | 100.0% |
| ORG | 3 | 100.0% |
| PERSON | 79 | 96.2% |
| SECRET | 5 | 100.0% |
