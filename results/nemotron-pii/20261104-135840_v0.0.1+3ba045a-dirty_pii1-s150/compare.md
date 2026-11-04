# Nemotron-PII benchmark · 200 test docs

Leak rate = share of gold PII characters left unmasked (lower is better). Core excludes weak quasi-identifiers (education_level, employment_status, language, occupation).

| model | leak ↓ | core leak ↓ | span recall ↑ | span precision ↑ | type acc ↑ | valid JSON | 1st try | hallucinated | p50 / p95 per doc | tokens in/out | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| glimmer-sampler `rohan-majji/run-3ae33b189bfd44bbb59217963a11fcfe/step-150-008d387b` | 9.8% | 2.5% | 90.1% | 95.5% | 99.4% | 100.0% | 100.0% | 4 | 10.5s / 41.4s | 711,573/36,042 | – |

## Recall by type

| type | glimmer-sampler |
|---|---|
| ADDRESS | 100.0% |
| CONTACT | 98.2% |
| DATE | 94.0% |
| ID | 100.0% |
| LOCATION | 88.6% |
| ORG | 100.0% |
| PERSON | 97.7% |
| SECRET | 100.0% |
| SENSITIVE_ATTRIBUTE | 39.2% |

## Recall by label

| label | n | glimmer-sampler |
|---|---|---|
| account_number | 32 | 100.0% |
| age | 7 | 85.7% |
| api_key | 8 | 100.0% |
| bank_routing_number | 19 | 100.0% |
| biometric_identifier | 29 | 100.0% |
| blood_type | 11 | 100.0% |
| certificate_license_number | 6 | 100.0% |
| city | 24 | 95.8% |
| company_name | 136 | 100.0% |
| coordinate | 16 | 81.2% |
| country | 33 | 93.9% |
| county | 25 | 68.0% |
| credit_debit_card | 24 | 100.0% |
| customer_id | 33 | 100.0% |
| cvv | 7 | 100.0% |
| date | 137 | 95.6% |
| date_of_birth | 36 | 100.0% |
| date_time | 26 | 96.2% |
| device_identifier | 7 | 100.0% |
| education_level | 14 | 7.1% |
| email | 113 | 96.5% |
| employee_id | 23 | 100.0% |
| employment_status | 17 | 11.8% |
| fax_number | 10 | 100.0% |
| first_name | 143 | 97.2% |
| gender | 19 | 89.5% |
| health_plan_beneficiary_number | 28 | 100.0% |
| http_cookie | 3 | 100.0% |
| ipv4 | 19 | 100.0% |
| ipv6 | 10 | 100.0% |
| language | 16 | 0.0% |
| last_name | 120 | 98.3% |
| license_plate | 8 | 100.0% |
| mac_address | 8 | 100.0% |
| medical_record_number | 21 | 100.0% |
| national_id | 5 | 100.0% |
| occupation | 78 | 1.3% |
| password | 20 | 100.0% |
| phone_number | 47 | 100.0% |
| pin | 16 | 100.0% |
| political_view | 12 | 100.0% |
| postcode | 15 | 100.0% |
| race_ethnicity | 8 | 100.0% |
| religious_belief | 13 | 100.0% |
| sexuality | 9 | 100.0% |
| ssn | 7 | 100.0% |
| state | 36 | 91.7% |
| street_address | 38 | 100.0% |
| swift_bic | 18 | 100.0% |
| tax_id | 3 | 100.0% |
| time | 69 | 87.0% |
| unique_id | 2 | 100.0% |
| url | 76 | 98.7% |
| user_name | 28 | 100.0% |
| vehicle_identifier | 10 | 100.0% |
