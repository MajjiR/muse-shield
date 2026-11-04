# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-resolution `accounts/rohan-majji/models/muse-shield-glimmer-er-v2b#accounts/rohan-majji/deployments/ms-eval-er-v2b-1105-0108` | 31.3% | 25.4% | 74.7% | 88.8% | 91.1% | 99.9% | 98.9% | 0 | 8.3s / 22.3s | 2,396,304/190,422 | – |

## Recall by type

| type | glimmer-resolution |
|---|---|
| ADDRESS | 90.5% |
| CONTACT | 74.6% |
| DATE | 73.6% |
| ID | 95.1% |
| LOCATION | 45.7% |
| ORG | 98.1% |
| PERSON | 97.9% |
| SECRET | 84.8% |
| SENSITIVE_ATTRIBUTE | 21.1% |

## Recall by label

| label | n | glimmer-resolution |
|---|---|---|
| account_number | 80 | 98.8% |
| age | 31 | 96.8% |
| api_key | 24 | 87.5% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 96.4% |
| blood_type | 33 | 78.8% |
| certificate_license_number | 14 | 92.9% |
| city | 83 | 54.2% |
| company_name | 314 | 98.1% |
| coordinate | 47 | 70.2% |
| country | 94 | 23.4% |
| county | 52 | 38.5% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 97.8% |
| cvv | 17 | 100.0% |
| date | 389 | 88.7% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 80.3% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 0.0% |
| email | 275 | 95.3% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 0.0% |
| fax_number | 30 | 93.3% |
| first_name | 415 | 99.0% |
| gender | 45 | 8.9% |
| health_plan_beneficiary_number | 67 | 98.5% |
| http_cookie | 17 | 52.9% |
| ipv4 | 29 | 75.9% |
| ipv6 | 14 | 71.4% |
| language | 52 | 5.8% |
| last_name | 304 | 96.4% |
| license_plate | 23 | 78.3% |
| mac_address | 14 | 92.9% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 93.3% |
| occupation | 185 | 4.3% |
| password | 47 | 83.0% |
| phone_number | 110 | 100.0% |
| pin | 33 | 93.9% |
| political_view | 31 | 48.4% |
| postcode | 25 | 80.0% |
| race_ethnicity | 27 | 55.6% |
| religious_belief | 32 | 31.2% |
| sexuality | 19 | 26.3% |
| ssn | 26 | 100.0% |
| state | 80 | 42.5% |
| street_address | 84 | 90.5% |
| swift_bic | 38 | 92.1% |
| tax_id | 6 | 100.0% |
| time | 130 | 7.7% |
| unique_id | 6 | 66.7% |
| url | 190 | 26.8% |
| user_name | 73 | 75.3% |
| vehicle_identifier | 30 | 80.0% |
