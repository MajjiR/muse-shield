# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/rohan-majji/models/muse-shield-glimmer-lora-v1d#accounts/rohan-majji/deployments/ms-eval-v1d` | 3.4% | 1.5% | 96.3% | 95.4% | 99.0% | 100.0% | 100.0% | 1 | 5.8s / 17.1s | 2,523,328/110,158 | $0.51 (GPU time) |

## Recall by type

| type | glimmer |
|---|---|
| ADDRESS | 98.8% |
| CONTACT | 99.4% |
| DATE | 95.2% |
| ID | 99.9% |
| LOCATION | 96.1% |
| ORG | 99.0% |
| PERSON | 99.0% |
| SECRET | 97.8% |
| SENSITIVE_ATTRIBUTE | 83.5% |

## Recall by label

| label | n | glimmer |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 90.3% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 100.0% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 97.6% |
| company_name | 314 | 99.0% |
| coordinate | 47 | 100.0% |
| country | 94 | 100.0% |
| county | 52 | 82.7% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 100.0% |
| date | 389 | 96.7% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 95.8% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 93.0% |
| email | 275 | 98.5% |
| employee_id | 53 | 98.1% |
| employment_status | 52 | 94.2% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.0% |
| gender | 45 | 97.8% |
| health_plan_beneficiary_number | 67 | 100.0% |
| http_cookie | 17 | 88.2% |
| ipv4 | 29 | 100.0% |
| ipv6 | 14 | 100.0% |
| language | 52 | 92.3% |
| last_name | 304 | 99.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 100.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 100.0% |
| occupation | 185 | 58.9% |
| password | 47 | 97.9% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 96.8% |
| postcode | 25 | 100.0% |
| race_ethnicity | 27 | 100.0% |
| religious_belief | 32 | 100.0% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 95.0% |
| street_address | 84 | 98.8% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 87.7% |
| unique_id | 6 | 100.0% |
| url | 190 | 100.0% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 100.0% |
