# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-resolution `muse-spark-1.3` | 9.0% | 1.9% | 90.9% | 82.6% | 96.8% | 100.0% | 100.0% | 0 | 63.6s / 203.5s | 4,671,753/3,467,896 | $20.58 |

## Recall by type

| type | glimmer-resolution |
|---|---|
| ADDRESS | 98.8% |
| CONTACT | 99.3% |
| DATE | 93.0% |
| ID | 99.6% |
| LOCATION | 96.6% |
| ORG | 97.5% |
| PERSON | 98.7% |
| SECRET | 98.6% |
| SENSITIVE_ATTRIBUTE | 45.5% |

## Recall by label

| label | n | glimmer-resolution |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 93.5% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 100.0% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 100.0% |
| company_name | 314 | 97.5% |
| coordinate | 47 | 100.0% |
| country | 94 | 100.0% |
| county | 52 | 82.7% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 100.0% |
| date | 389 | 94.6% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 97.2% |
| device_identifier | 10 | 100.0% |
| education_level | 43 | 4.7% |
| email | 275 | 98.2% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 15.4% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.3% |
| gender | 45 | 100.0% |
| health_plan_beneficiary_number | 67 | 98.5% |
| http_cookie | 17 | 94.1% |
| ipv4 | 29 | 100.0% |
| ipv6 | 14 | 100.0% |
| language | 52 | 9.6% |
| last_name | 304 | 98.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 100.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 93.3% |
| occupation | 185 | 11.4% |
| password | 47 | 97.9% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 100.0% |
| postcode | 25 | 100.0% |
| race_ethnicity | 27 | 92.6% |
| religious_belief | 32 | 100.0% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 95.0% |
| street_address | 84 | 98.8% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 81.5% |
| unique_id | 6 | 100.0% |
| url | 190 | 100.0% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 96.7% |
