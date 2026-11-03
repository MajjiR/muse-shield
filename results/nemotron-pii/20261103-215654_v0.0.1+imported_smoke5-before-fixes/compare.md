# Nemotron-PII benchmark · 5 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/fireworks/models/muse-glimmer-30b` | 100.0% | 100.0% | 0.0% | – | – | – | – | 0 | 1.8s / 2.1s | 0/0 | $0.00 |
| muse_spark `muse-spark-1.3` | 95.8% | 95.5% | 4.8% | 100.0% | 100.0% | 42.0% | 42.0% | 0 | 108.5s / 140.0s | 52,542/76,587 | – |
| muse_wonder `muse-wonder-1.0` | 40.4% | 36.5% | 61.3% | 95.0% | 100.0% | 86.0% | 68.0% | 0 | 81.1s / 84.4s | 43,825/56,556 | – |

## Recall by type

| type | glimmer | muse_spark | muse_wonder |
|---|---|---|---|
| ADDRESS | 0.0% | 0.0% | 100.0% |
| CONTACT | 0.0% | 7.1% | 78.6% |
| DATE | 0.0% | 0.0% | 0.0% |
| ID | 0.0% | 5.9% | 70.6% |
| LOCATION | 0.0% | 0.0% | 100.0% |
| ORG | 0.0% | 0.0% | 73.3% |
| PERSON | 0.0% | 50.0% | 100.0% |
| SENSITIVE_ATTRIBUTE | 0.0% | 0.0% | 0.0% |

## Recall by label

| label | n | glimmer | muse_spark | muse_wonder |
|---|---|---|---|---|
| bank_routing_number | 1 | 0.0% | 0.0% | 100.0% |
| company_name | 15 | 0.0% | 0.0% | 73.3% |
| county | 1 | 0.0% | 0.0% | 100.0% |
| credit_debit_card | 5 | 0.0% | 0.0% | 60.0% |
| date | 1 | 0.0% | 0.0% | 0.0% |
| education_level | 1 | 0.0% | 0.0% | 0.0% |
| email | 8 | 0.0% | 12.5% | 87.5% |
| first_name | 1 | 0.0% | 100.0% | 100.0% |
| gender | 6 | 0.0% | 0.0% | 0.0% |
| health_plan_beneficiary_number | 1 | 0.0% | 100.0% | 100.0% |
| language | 2 | 0.0% | 0.0% | 0.0% |
| last_name | 1 | 0.0% | 0.0% | 100.0% |
| license_plate | 1 | 0.0% | 0.0% | 100.0% |
| mac_address | 1 | 0.0% | 0.0% | 100.0% |
| occupation | 1 | 0.0% | 0.0% | 0.0% |
| phone_number | 3 | 0.0% | 0.0% | 100.0% |
| ssn | 1 | 0.0% | 0.0% | 0.0% |
| street_address | 1 | 0.0% | 0.0% | 100.0% |
| swift_bic | 6 | 0.0% | 0.0% | 66.7% |
| time | 1 | 0.0% | 0.0% | 0.0% |
| url | 2 | 0.0% | 0.0% | 0.0% |
| user_name | 1 | 0.0% | 0.0% | 100.0% |
| vehicle_identifier | 1 | 0.0% | 0.0% | 100.0% |

