# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| muse_spark `muse-spark-1.3-contributor` | 16.7% | 14.6% | 82.1% | 85.9% | 97.9% | 100.0% | 99.9% | 2 | 54.2s / 182.4s | 2,142,524/5,019,815 | $1.06 |

## Recall by type

| type | muse_spark |
|---|---|
| ADDRESS | 98.8% |
| CONTACT | 96.9% |
| DATE | 35.1% |
| ID | 95.7% |
| LOCATION | 77.7% |
| ORG | 98.7% |
| PERSON | 99.9% |
| SECRET | 90.6% |
| SENSITIVE_ATTRIBUTE | 69.1% |

## Recall by label

| label | n | muse_spark |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 96.8% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 96.4% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 92.9% |
| city | 83 | 90.4% |
| company_name | 314 | 98.7% |
| coordinate | 47 | 36.2% |
| country | 94 | 87.2% |
| county | 52 | 61.5% |
| credit_debit_card | 58 | 98.3% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 94.1% |
| date | 389 | 28.3% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 19.7% |
| device_identifier | 10 | 70.0% |
| education_level | 43 | 79.1% |
| email | 275 | 97.8% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 71.2% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.8% |
| gender | 45 | 93.3% |
| health_plan_beneficiary_number | 67 | 100.0% |
| http_cookie | 17 | 47.1% |
| ipv4 | 29 | 75.9% |
| ipv6 | 14 | 64.3% |
| language | 52 | 17.3% |
| last_name | 304 | 100.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 57.1% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 100.0% |
| occupation | 185 | 47.0% |
| password | 47 | 93.6% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 96.8% |
| postcode | 25 | 88.0% |
| race_ethnicity | 27 | 100.0% |
| religious_belief | 32 | 100.0% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 85.0% |
| street_address | 84 | 98.8% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 22.3% |
| unique_id | 6 | 83.3% |
| url | 190 | 92.1% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 83.3% |
