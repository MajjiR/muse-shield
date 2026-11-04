# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer `accounts/rohan-majji/models/muse-shield-glimmer-lora-v1c#accounts/rohan-majji/deployments/ms-eval-v1c` | 3.0% | 1.4% | 96.3% | 97.2% | 99.1% | 100.0% | 100.0% | 2 | 5.6s / 16.9s | 2,523,328/108,821 | $0.50 (GPU time) |

## Recall by type

| type | glimmer |
|---|---|
| ADDRESS | 98.8% |
| CONTACT | 99.3% |
| DATE | 94.1% |
| ID | 99.9% |
| LOCATION | 95.8% |
| ORG | 99.7% |
| PERSON | 99.7% |
| SECRET | 99.3% |
| SENSITIVE_ATTRIBUTE | 83.5% |

## Recall by label

| label | n | glimmer |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 90.3% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 100.0% |
| blood_type | 33 | 97.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 97.6% |
| company_name | 314 | 99.7% |
| coordinate | 47 | 100.0% |
| country | 94 | 100.0% |
| county | 52 | 80.8% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 98.9% |
| cvv | 17 | 100.0% |
| date | 389 | 94.3% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 97.2% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 93.0% |
| email | 275 | 98.5% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 98.1% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.5% |
| gender | 45 | 97.8% |
| health_plan_beneficiary_number | 67 | 100.0% |
| http_cookie | 17 | 100.0% |
| ipv4 | 29 | 100.0% |
| ipv6 | 14 | 100.0% |
| language | 52 | 92.3% |
| last_name | 304 | 100.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 100.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 100.0% |
| occupation | 185 | 57.8% |
| password | 47 | 97.9% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 100.0% |
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
| url | 190 | 99.5% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 100.0% |
