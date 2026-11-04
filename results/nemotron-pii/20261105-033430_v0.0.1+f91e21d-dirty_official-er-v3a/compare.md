# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-resolution `accounts/rohan-majji/models/muse-shield-glimmer-er-v3a-s250#accounts/rohan-majji/deployments/ms-ck-er-v3a-s250-033151` | 9.5% | 2.0% | 90.6% | 91.9% | 99.0% | 100.0% | 100.0% | 0 | 9.6s / 26.6s | 2,950,553/203,515 | – |

## Recall by type

| type | glimmer-resolution |
|---|---|
| ADDRESS | 97.6% |
| CONTACT | 99.1% |
| DATE | 93.0% |
| ID | 99.3% |
| LOCATION | 95.5% |
| ORG | 97.8% |
| PERSON | 99.6% |
| SECRET | 99.3% |
| SENSITIVE_ATTRIBUTE | 42.7% |

## Recall by label

| label | n | glimmer-resolution |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 96.8% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 95.0% |
| biometric_identifier | 56 | 100.0% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 98.8% |
| company_name | 314 | 97.8% |
| coordinate | 47 | 97.9% |
| country | 94 | 98.9% |
| county | 52 | 80.8% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 100.0% |
| date | 389 | 93.8% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 97.2% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 2.3% |
| email | 275 | 98.5% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 0.0% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.5% |
| gender | 45 | 93.3% |
| health_plan_beneficiary_number | 67 | 98.5% |
| http_cookie | 17 | 100.0% |
| ipv4 | 29 | 100.0% |
| ipv6 | 14 | 100.0% |
| language | 52 | 17.3% |
| last_name | 304 | 99.7% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 100.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 93.3% |
| occupation | 185 | 6.5% |
| password | 47 | 97.9% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 100.0% |
| postcode | 25 | 100.0% |
| race_ethnicity | 27 | 100.0% |
| religious_belief | 32 | 96.9% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 95.0% |
| street_address | 84 | 97.6% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 83.8% |
| unique_id | 6 | 100.0% |
| url | 190 | 99.5% |
| user_name | 73 | 98.6% |
| vehicle_identifier | 30 | 96.7% |
