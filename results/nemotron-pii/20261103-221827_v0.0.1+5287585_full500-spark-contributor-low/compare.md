# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| muse_spark `muse-spark-1.3-contributor` | 15.8% | 14.0% | 83.0% | 86.5% | 97.9% | 100.0% | 100.0% | 1 | 32.4s / 114.2s | 2,139,434/2,781,296 | $0.61 |

## Recall by type

| type | muse_spark |
|---|---|
| ADDRESS | 97.6% |
| CONTACT | 96.9% |
| DATE | 36.7% |
| ID | 96.4% |
| LOCATION | 77.2% |
| ORG | 99.4% |
| PERSON | 99.9% |
| SECRET | 93.5% |
| SENSITIVE_ATTRIBUTE | 72.4% |

## Recall by label

| label | n | muse_spark |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 96.8% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 98.2% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 100.0% |
| city | 83 | 91.6% |
| company_name | 314 | 99.4% |
| coordinate | 47 | 31.9% |
| country | 94 | 88.3% |
| county | 52 | 55.8% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 100.0% |
| date | 389 | 27.8% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 29.6% |
| device_identifier | 10 | 80.0% |
| education_level | 43 | 74.4% |
| email | 275 | 98.2% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 80.8% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.8% |
| gender | 45 | 100.0% |
| health_plan_beneficiary_number | 67 | 100.0% |
| http_cookie | 17 | 52.9% |
| ipv4 | 29 | 72.4% |
| ipv6 | 14 | 57.1% |
| language | 52 | 25.0% |
| last_name | 304 | 100.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 57.1% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 100.0% |
| occupation | 185 | 50.8% |
| password | 47 | 97.9% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 100.0% |
| postcode | 25 | 88.0% |
| race_ethnicity | 27 | 100.0% |
| religious_belief | 32 | 100.0% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 86.2% |
| street_address | 84 | 97.6% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 26.9% |
| unique_id | 6 | 100.0% |
| url | 190 | 91.6% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 90.0% |
