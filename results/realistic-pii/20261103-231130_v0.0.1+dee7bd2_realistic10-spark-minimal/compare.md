# Realistic PII loop · 10 examples × 3 rounds

model `muse-spark-1.3` (reasoning minimal) · 160.3s · $0.1414

**Missed 3 of 231 must-mask values (1.3% leak).** Valid analysis 100.0%.

| type | recall | misses |
|---|---|---|
| ADDRESS | 100.0% | 0 |
| AMOUNT | 100.0% | 0 |
| CONTACT | 100.0% | 0 |
| DATE | 100.0% | 0 |
| ID | 100.0% | 0 |
| ORG | 100.0% | 0 |
| PERSON | 100.0% | 0 |
| SECRET | 80.0% | 3 |
| SENSITIVE_ATTRIBUTE | 100.0% | 0 |

## Values missed (times out of rounds)

- `card-support-chat` · **cvv 312** · 3/3

## Per example (last round)

### hr-transfer

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Pune, 1 December, HDFC Bank; left visible: none
- must stay readable: n/a
- extra masked: HR Business Partner
- contexts: HR (expected HR)

```
Hi <PERSON_1>,

<HR_1>

Please update his bank details: <ORG_1>, account <ID_2>, IFSC <ID_3>. His PAN is <ID_4>.

<HR_2>

Thanks,
<PERSON_3>
<SENSITIVE_ATTRIBUTE_1>, <ORG_2>
```

### medical-intake

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: metformin 500 mg, Star Health; left visible: none
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Patient: <PERSON_1>, DOB <DATE_1>, MRN <ID_1>.
Address: <ADDRESS_1>. Phone: <CONTACT_1>.

Presenting with <SENSITIVE_ATTRIBUTE_1> and <SENSITIVE_ATTRIBUTE_2>. Currently on <SENSITIVE_ATTRIBUTE_3>.

Insurance: <ORG_1> policy <ID_2>. Emergency contact: her husband <PERSON_2>, <CONTACT_2>.
```

### card-support-chat

- missed: cvv 312
- partly covered: none
- type mismatches: none
- optional masked: 09/27, ₹1,299, Swiggy; left visible: none
- must stay readable: n/a
- extra masked: yesterday
- contexts: none (expected none)

```
[10:42] Customer: hi my card got blocked, number is <ID_1>, expiry <DATE_1>, cvv <SECRET_1>
[10:43] Agent (<PERSON_1>): Hi! Can you confirm your registered mobile and the last transaction?
[10:44] Customer: <CONTACT_1>, i paid <PRICE_1> to <ORG_1> <DATE_2>. my UPI is <CONTACT_2>
[10:45] Customer: also my netbanking password is <SECRET_2> if that helps
```

### board-term-sheet

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 15 January 2027; left visible: none
- must stay readable: n/a
- extra masked: Board of Directors, General Counsel
- contexts: DEAL, DECISION (expected DEAL)

```
PRIVILEGED & CONFIDENTIAL

To: <ORG_1>, <ORG_2>
From: <PERSON_1>, <SENSITIVE_ATTRIBUTE_1>

<DEAL_1>

<DECISION_1> Please do not discuss this outside the board.
```

### travel-booking

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 2031-05-19, 12 Dec 2026, 23 Old Airport Road, 4421, The Leela Palace Bengaluru; left visible: LH 761
- must stay readable: n/a
- extra masked: Bengaluru, Frankfurt, Nigeria
- contexts: none (expected none)

```
Booking ref: <ID_1>
Passenger: <PERSON_1>
Passport: <ID_2> (<LOCATION_1>), expires <DATE_1>
Flight: LH 761 <LOCATION_2> to <LOCATION_3>, <DATE_2>, seat 14C

Hotel: <ORG_1>, <ADDRESS_1>. Paid with <ID_3>.
Contact: <CONTACT_1>, <CONTACT_2>
```

### incident-secrets

- missed: none
- partly covered: none
- type mismatches: 203.0.113.45 ID→CONTACT
- optional masked: none; left visible: INC-4471, acme-prod-backups, 2 Nov
- must stay readable: n/a
- extra masked: admin
- contexts: none (expected none)

```
Incident INC-4471: production outage on 2 Nov

Root cause: a leaked AWS key <SECRET_1> was used from IP <CONTACT_1> to delete the S3 bucket acme-prod-backups.

The on-call engineer, <PERSON_1> (<CONTACT_2>), rotated the key. Our Stripe secret <SECRET_2> was also in the same .env file and has been revoked.

Database host: <CONTACT_3>, user <CONTACT_4>, password <SECRET_3>.
```

### tax-question

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Infosys, SBI; left visible: none
- must stay readable: how much tax I'll owe under the new regime (kept)
- extra masked: none
- contexts: none (expected none)

```
Hi, I'm <PERSON_1>. My Aadhaar is <ID_1> and PAN <ID_2>.

Last year I earned <SALARY_1> from <ORG_1> and <REVENUE_1> rent from my flat at <ADDRESS_1>. I also have a home loan of <LOAN_1> with <ORG_2>.

Can you tell me how much tax I'll owe under the new regime?
```

### school-letter

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Class 4B; left visible: roll no. 17
- must stay readable: n/a
- extra masked: Principal
- contexts: none (expected none)

```
Dear <PERSON_1>,

Your son <PERSON_2> (<ID_1>, roll no. <ID_2>) was seen by the school counsellor today after an incident with another student. He mentioned he has been diagnosed with <SENSITIVE_ATTRIBUTE_1>.

Please call me at <CONTACT_1> or reply to <CONTACT_2>.

Regards,
<PERSON_3>, <SENSITIVE_ATTRIBUTE_2>
```

### flat-negotiation

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: ₹1.75, 1.7 final, Diwali; left visible: none
- must stay readable: n/a
- extra masked: Rahul
- contexts: NEGOTIATION (expected NEGOTIATION)

```
<NEGOTIATION_1> My number for the agreement is <CONTACT_1>
<PERSON_1>: done, his name is <PERSON_2>, PAN on the sale deed will be <ID_1>
```

### gst-invoice

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: INV-2026-0912, ICICI Bank; left visible: none
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Tax Invoice #<ID_1>
Vendor: <ORG_1>, GSTIN <ID_2>, <ADDRESS_1>
Bill to: <ORG_2>, GSTIN <ID_3>

Freight charges for October: <FEE_1> + 18% GST = <FEE_2>.
Pay to: <ORG_3> A/c <ID_4>, IFSC <ID_5>.
Contact: <CONTACT_1> / <PERSON_1>, <CONTACT_2>
```

