# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ljrd6tyj` | 21.1% | 17.5% | 77.6% | 89.1% | 96.1% | 97.3% | 97.0% | 6 | 5.8s / 36.3s | 2,267,560/446,968 | – |

## Recall by type

| type | glimmer |
|---|---|
| ADDRESS | 96.4% |
| CONTACT | 87.6% |
| DATE | 57.4% |
| ID | 87.0% |
| LOCATION | 82.2% |
| ORG | 89.8% |
| PERSON | 86.0% |
| SECRET | 81.9% |
| SENSITIVE_ATTRIBUTE | 52.4% |

## Recall by label

| label | n | glimmer |
|---|---|---|
| account_number | 80 | 90.0% |
| age | 31 | 83.9% |
| api_key | 24 | 75.0% |
| bank_routing_number | 40 | 95.0% |
| biometric_identifier | 56 | 82.1% |
| blood_type | 33 | 87.9% |
| certificate_license_number | 14 | 71.4% |
| city | 83 | 81.9% |
| company_name | 314 | 89.8% |
| coordinate | 47 | 80.9% |
| country | 94 | 78.7% |
| county | 52 | 78.8% |
| credit_debit_card | 58 | 89.7% |
| customer_id | 92 | 93.5% |
| cvv | 17 | 82.4% |
| date | 389 | 58.6% |
| date_of_birth | 83 | 95.2% |
| date_time | 71 | 49.3% |
| device_identifier | 10 | 70.0% |
| education_level | 43 | 53.5% |
| email | 275 | 89.1% |
| employee_id | 53 | 88.7% |
| employment_status | 52 | 21.2% |
| fax_number | 30 | 80.0% |
| first_name | 415 | 82.4% |
| gender | 45 | 68.9% |
| health_plan_beneficiary_number | 67 | 91.0% |
| http_cookie | 17 | 58.8% |
| ipv4 | 29 | 65.5% |
| ipv6 | 14 | 42.9% |
| language | 52 | 30.8% |
| last_name | 304 | 90.8% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 78.6% |
| medical_record_number | 57 | 84.2% |
| national_id | 15 | 86.7% |
| occupation | 185 | 35.7% |
| password | 47 | 89.4% |
| phone_number | 110 | 93.6% |
| pin | 33 | 87.9% |
| political_view | 31 | 80.6% |
| postcode | 25 | 92.0% |
| race_ethnicity | 27 | 77.8% |
| religious_belief | 32 | 75.0% |
| sexuality | 19 | 84.2% |
| ssn | 26 | 84.6% |
| state | 80 | 86.2% |
| street_address | 84 | 96.4% |
| swift_bic | 38 | 86.8% |
| tax_id | 6 | 100.0% |
| time | 130 | 33.8% |
| unique_id | 6 | 83.3% |
| url | 190 | 87.4% |
| user_name | 73 | 76.7% |
| vehicle_identifier | 30 | 93.3% |

