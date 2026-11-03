# Nemotron-PII benchmark · 500 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| muse_spark `muse-spark-1.3-contributor` | 16.6% | 14.8% | 82.0% | 86.3% | 97.9% | 100.0% | 100.0% | 0 | 62.2s / 217.3s | 2,139,434/4,534,631 | $0.96 |

## Recall by type

| type | muse_spark |
|---|---|
| ADDRESS | 98.8% |
| CONTACT | 96.8% |
| DATE | 34.8% |
| ID | 95.6% |
| LOCATION | 75.6% |
| ORG | 98.4% |
| PERSON | 99.9% |
| SECRET | 91.3% |
| SENSITIVE_ATTRIBUTE | 70.2% |

## Recall by label

| label | n | muse_spark |
|---|---|---|
| account_number | 80 | 100.0% |
| age | 31 | 96.8% |
| api_key | 24 | 100.0% |
| bank_routing_number | 40 | 100.0% |
| biometric_identifier | 56 | 98.2% |
| blood_type | 33 | 100.0% |
| certificate_license_number | 14 | 92.9% |
| city | 83 | 85.5% |
| company_name | 314 | 98.4% |
| coordinate | 47 | 31.9% |
| country | 94 | 85.1% |
| county | 52 | 61.5% |
| credit_debit_card | 58 | 100.0% |
| customer_id | 92 | 100.0% |
| cvv | 17 | 94.1% |
| date | 389 | 28.0% |
| date_of_birth | 83 | 100.0% |
| date_time | 71 | 21.1% |
| device_identifier | 10 | 60.0% |
| education_level | 43 | 72.1% |
| email | 275 | 98.5% |
| employee_id | 53 | 100.0% |
| employment_status | 52 | 78.8% |
| fax_number | 30 | 100.0% |
| first_name | 415 | 99.8% |
| gender | 45 | 86.7% |
| health_plan_beneficiary_number | 67 | 100.0% |
| http_cookie | 17 | 47.1% |
| ipv4 | 29 | 72.4% |
| ipv6 | 14 | 64.3% |
| language | 52 | 19.2% |
| last_name | 304 | 100.0% |
| license_plate | 23 | 100.0% |
| mac_address | 14 | 50.0% |
| medical_record_number | 57 | 100.0% |
| national_id | 15 | 100.0% |
| occupation | 185 | 50.8% |
| password | 47 | 95.7% |
| phone_number | 110 | 100.0% |
| pin | 33 | 100.0% |
| political_view | 31 | 96.8% |
| postcode | 25 | 92.0% |
| race_ethnicity | 27 | 100.0% |
| religious_belief | 32 | 100.0% |
| sexuality | 19 | 100.0% |
| ssn | 26 | 100.0% |
| state | 80 | 83.8% |
| street_address | 84 | 98.8% |
| swift_bic | 38 | 100.0% |
| tax_id | 6 | 100.0% |
| time | 130 | 20.8% |
| unique_id | 6 | 83.3% |
| url | 190 | 90.5% |
| user_name | 73 | 100.0% |
| vehicle_identifier | 30 | 83.3% |
