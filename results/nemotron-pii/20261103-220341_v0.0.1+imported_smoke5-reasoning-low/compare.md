# Nemotron-PII benchmark · 5 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ljrd6tyj` | 22.5% | 17.4% | 71.0% | 75.9% | 97.7% | 92.0% | 92.0% | 0 | 20.0s / 31.5s | 35,966/11,048 | $0.03 |
| muse_spark `muse-spark-1.3` | 9.9% | 7.6% | 85.5% | 89.6% | 100.0% | 100.0% | 100.0% | 1 | 67.6s / 106.8s | 32,332/42,211 | – |
| muse_wonder `muse-wonder-1.0` | 12.2% | 6.5% | 80.6% | 76.5% | 100.0% | 100.0% | 100.0% | 1 | 37.3s / 48.3s | 32,332/17,983 | – |

## Recall by type

| type | glimmer | muse_spark | muse_wonder |
|---|---|---|---|
| ADDRESS | 100.0% | 100.0% | 100.0% |
| CONTACT | 92.9% | 92.9% | 92.9% |
| DATE | 100.0% | 0.0% | 0.0% |
| ID | 82.4% | 88.2% | 100.0% |
| LOCATION | 100.0% | 100.0% | 100.0% |
| ORG | 80.0% | 100.0% | 100.0% |
| PERSON | 50.0% | 100.0% | 100.0% |
| SENSITIVE_ATTRIBUTE | 0.0% | 60.0% | 10.0% |

## Recall by label

| label | n | glimmer | muse_spark | muse_wonder |
|---|---|---|---|---|
| bank_routing_number | 1 | 100.0% | 100.0% | 100.0% |
| company_name | 15 | 80.0% | 100.0% | 100.0% |
| county | 1 | 100.0% | 100.0% | 100.0% |
| credit_debit_card | 5 | 80.0% | 100.0% | 100.0% |
| date | 1 | 100.0% | 0.0% | 0.0% |
| education_level | 1 | 0.0% | 0.0% | 0.0% |
| email | 8 | 87.5% | 87.5% | 87.5% |
| first_name | 1 | 100.0% | 100.0% | 100.0% |
| gender | 6 | 0.0% | 83.3% | 16.7% |
| health_plan_beneficiary_number | 1 | 100.0% | 100.0% | 100.0% |
| language | 2 | 0.0% | 0.0% | 0.0% |
| last_name | 1 | 0.0% | 100.0% | 100.0% |
| license_plate | 1 | 100.0% | 100.0% | 100.0% |
| mac_address | 1 | 100.0% | 0.0% | 100.0% |
| occupation | 1 | 0.0% | 100.0% | 0.0% |
| phone_number | 3 | 100.0% | 100.0% | 100.0% |
| ssn | 1 | 0.0% | 100.0% | 100.0% |
| street_address | 1 | 100.0% | 100.0% | 100.0% |
| swift_bic | 6 | 83.3% | 100.0% | 100.0% |
| time | 1 | 100.0% | 0.0% | 0.0% |
| url | 2 | 100.0% | 100.0% | 100.0% |
| user_name | 1 | 100.0% | 100.0% | 100.0% |
| vehicle_identifier | 1 | 100.0% | 0.0% | 100.0% |

