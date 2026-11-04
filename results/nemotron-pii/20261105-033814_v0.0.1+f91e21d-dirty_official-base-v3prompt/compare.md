# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-resolution `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ms-off-base-033430` | 11.7% | 5.6% | 87.9% | 83.9% | 95.2% | 100.0% | 99.9% | 0 | 15.1s / 222.0s | 4,708,194/616,186 | – |

## Recall by type

| type | glimmer-resolution |
|---|---|
| ADDRESS | 95.2% |
| CONTACT | 97.3% |
| DATE | 84.5% |
| ID | 98.2% |
| LOCATION | 91.6% |
| ORG | 93.6% |
| PERSON | 96.2% |
| SECRET | 94.2% |
| SENSITIVE_ATTRIBUTE | 47.1% |

## Recall by label

| label | n | glimmer-resolution |
|---|---|---|
| account_number | 80 | 97.5% |
| age | 31 | 96.8% |
| api_key | 24 | 87.5% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 98.2% |
| blood_type | 33 | 97.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 94.0% |
| company_name | 314 | 93.6% |
| coordinate | 47 | 93.6% |
| country | 94 | 94.7% |
| county | 52 | 78.8% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 98.9% |
| cvv | 17 | 100.0% |
| date | 389 | 83.0% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 95.8% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 46.5% |
| email | 275 | 97.1% |
| employee_id | 53 | 98.1% |
| employment_status | 52 | 11.5% |
| fax_number | 30 | 96.7% |
| first_name | 415 | 96.6% |
| gender | 45 | 80.0% |
| health_plan_beneficiary_number | 67 | 98.5% |
| http_cookie | 17 | 76.5% |
| ipv4 | 29 | 86.2% |
| ipv6 | 14 | 92.9% |
| language | 52 | 21.2% |
| last_name | 304 | 95.7% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 100.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 93.3% |
| occupation | 185 | 12.4% |
| password | 47 | 97.9% |
| phone_number | 110 | 99.1% |
| pin | 33 | 100.0% |
| political_view | 31 | 100.0% |
| postcode | 25 | 92.0% |
| race_ethnicity | 27 | 96.3% |
| religious_belief | 32 | 96.9% |
| sexuality | 19 | 68.4% |
| ssn | 26 | 100.0% |
| state | 80 | 92.5% |
| street_address | 84 | 95.2% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 73.1% |
| unique_id | 6 | 100.0% |
| url | 190 | 97.4% |
| user_name | 73 | 95.9% |
| vehicle_identifier | 30 | 96.7% |
