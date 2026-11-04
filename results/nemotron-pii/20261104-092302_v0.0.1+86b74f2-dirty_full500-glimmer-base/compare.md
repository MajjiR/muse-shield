# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ms-eval-base` | 16.9% | 10.6% | 81.5% | 89.6% | 95.8% | 99.5% | 99.4% | 9 | 3.4s / 21.7s | 2,543,293/213,493 | $0.46 (GPU time) |

## Recall by type

| type | glimmer |
|---|---|
| ADDRESS | 100.0% |
| CONTACT | 96.0% |
| DATE | 61.7% |
| ID | 96.6% |
| LOCATION | 88.7% |
| ORG | 94.9% |
| PERSON | 89.8% |
| SECRET | 91.3% |
| SENSITIVE_ATTRIBUTE | 38.7% |

## Recall by label

| label | n | glimmer |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 83.9% |
| api_key | 24 | 83.3% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 98.2% |
| blood_type | 33 | 90.9% |
| certificate_license_number | 14 | 92.9% |
| city | 83 | 90.4% |
| company_name | 314 | 94.9% |
| coordinate | 47 | 87.2% |
| country | 94 | 87.2% |
| county | 52 | 78.8% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 97.8% |
| cvv | 17 | 94.1% |
| date | 389 | 63.5% |
| date_of_birth | 83 | 97.6% |
| date_time | 71 | 63.4% |
| device_identifier | 10 | 80.0% |
| education_level | 43 | 16.3% |
| email | 275 | 96.4% |
| employee_id | 53 | 96.2% |
| employment_status | 52 | 1.9% |
| fax_number | 30 | 93.3% |
| first_name | 415 | 85.1% |
| gender | 45 | 60.0% |
| health_plan_beneficiary_number | 67 | 98.5% |
| http_cookie | 17 | 76.5% |
| ipv4 | 29 | 79.3% |
| ipv6 | 14 | 71.4% |
| language | 52 | 23.1% |
| last_name | 304 | 96.4% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 78.6% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 93.3% |
| occupation | 185 | 12.4% |
| password | 47 | 93.6% |
| phone_number | 110 | 98.2% |
| pin | 33 | 100.0% |
| political_view | 31 | 77.4% |
| postcode | 25 | 100.0% |
| race_ethnicity | 27 | 88.9% |
| religious_belief | 32 | 84.4% |
| sexuality | 19 | 63.2% |
| ssn | 26 | 100.0% |
| state | 80 | 92.5% |
| street_address | 84 | 100.0% |
| swift_bic | 38 | 94.7% |
| tax_id | 6 | 100.0% |
| time | 130 | 32.3% |
| unique_id | 6 | 100.0% |
| url | 190 | 95.8% |
| user_name | 73 | 93.2% |
| vehicle_identifier | 30 | 100.0% |
