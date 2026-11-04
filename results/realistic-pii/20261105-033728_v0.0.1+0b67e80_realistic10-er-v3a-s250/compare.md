# Realistic PII loop · 10 examples × 2 rounds

model `accounts/rohan-majji/models/muse-shield-glimmer-er-v3a-s250#accounts/rohan-majji/deployments/ms-er-cmp-er-v3a-s250-1105-0331` (reasoning None) · 176.8s · $0.0000

**Missed 2 of 154 must-mask values (1.3% leak).** Valid analysis 100.0%.

| type | recall | misses |
|---|---|---|
| ADDRESS | 100.0% | 0 |
| AMOUNT | 100.0% | 0 |
| CONTACT | 100.0% | 0 |
| DATE | 100.0% | 0 |
| ID | 100.0% | 0 |
| ORG | 100.0% | 0 |
| PERSON | 94.4% | 2 |
| SECRET | 100.0% | 0 |
| SENSITIVE_ATTRIBUTE | 100.0% | 0 |

## Values missed (times out of rounds)

- `flat-negotiation` · **Rahul** · 2/2

## Per example (last round)

### hr-transfer

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Pune, 1 December, HDFC Bank; left visible: none
- must stay readable: n/a
- extra masked: none
- contexts: none (expected HR)

```
Hi <PERSON_1>,

Following our call, I'm confirming that <PERSON_2> (Employee ID <ID_1>) will move to the <LOCATION_1> office from <DATE_1>. His revised CTC is <SALARY_1>.

Please update his bank details: <ORG_1>, account <ID_2>, IFSC <ID_3>. His PAN is <ID_4>.

Keep this confidential until the reorg is announced.

Thanks,
<PERSON_3>
HR Business Partner, <ORG_2>
```

### medical-intake

- missed: none
- partly covered: 44 Lake Road, Kochi 682011 (88%), mild hypertension (71%)
- type mismatches: none
- optional masked: Star Health; left visible: metformin 500 mg
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Patient: <PERSON_1>, DOB <DATE_1>, MRN <ID_1>.
Address: <ADDRESS_1>, <LOCATION_1> <LOCATION_2>. Phone: <CONTACT_1>.

Presenting with <SENSITIVE_ATTRIBUTE_1> and mild <SENSITIVE_ATTRIBUTE_2>. Currently on metformin 500 mg twice daily.

Insurance: <ORG_1> policy <ID_2>. Emergency contact: her husband <PERSON_2>, <CONTACT_2>.
```

### card-support-chat

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 09/27, ₹1,299, Swiggy; left visible: none
- must stay readable: n/a
- extra masked: 10:42, 10:43, 10:44, 10:45
- contexts: none (expected none)

```
[<DATE_1>] Customer: hi my card got blocked, number is <ID_1>, expiry <DATE_2>, cvv <SECRET_1>
[<DATE_3>] Agent (<PERSON_1>): Hi! Can you confirm your registered mobile and the last transaction?
[<DATE_4>] Customer: <CONTACT_1>, i paid <AMOUNT_1> to <ORG_1> yesterday. my UPI is <CONTACT_2>
[<DATE_5>] Customer: also my netbanking password is <SECRET_2> if that helps
```

### board-term-sheet

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 15 January 2027; left visible: none
- must stay readable: n/a
- extra masked: Corvex
- contexts: none (expected DEAL)

```
PRIVILEGED & CONFIDENTIAL

To: Board of Directors, <ORG_1>
From: <PERSON_1>, General Counsel

We have received a non-binding term sheet from <ORG_2> valuing the company at <DEAL_VALUE_1> pre-money, with a <DEAL_VALUE_2> Series B led by <ORG_2>. Closing is targeted for <DATE_1>.

The founders, <PERSON_2> and <PERSON_3>, will retain board seats. Please do not discuss this outside the board.
```

### travel-booking

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 2031-05-19, LH 761, 12 Dec 2026, 23 Old Airport Road, 4421; left visible: The Leela Palace Bengaluru
- must stay readable: n/a
- extra masked: 14C, Bengaluru, Frankfurt, Nigeria, Visa
- contexts: none (expected none)

```
Booking ref: <ID_1>
Passenger: Mr. <PERSON_1>
Passport: <ID_2> (<LOCATION_1>), expires <DATE_1>
Flight: <ID_3> <LOCATION_2> to <LOCATION_3>, <DATE_2>, seat <ID_4>

Hotel: The Leela Palace Bengaluru, <ADDRESS_1>. Paid with <ORG_1> ending <ID_5>.
Contact: <CONTACT_1>, <CONTACT_2>
```

### incident-secrets

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: acme-prod-backups, 2 Nov; left visible: INC-4471
- must stay readable: n/a
- extra masked: Stripe
- contexts: none (expected none)

```
Incident INC-4471: production outage on <DATE_1>

Root cause: a leaked AWS key <SECRET_1> was used from IP <ID_1> to delete the S3 bucket <ID_2>.

The on-call engineer, <PERSON_1> (<CONTACT_1>), rotated the key. Our <ORG_1> secret <SECRET_2> was also in the same .env file and has been revoked.

Database host: <CONTACT_2>, user admin, password <SECRET_3>.
```

### tax-question

- missed: none
- partly covered: B-302, Sai Residency, Hyderabad 500032 (87%)
- type mismatches: none
- optional masked: Infosys, SBI; left visible: none
- must stay readable: how much tax I'll owe under the new regime (kept)
- extra masked: none
- contexts: none (expected none)

```
Hi, I'm <PERSON_1>. My Aadhaar is <ID_1> and PAN <ID_2>.

Last year I earned <SALARY_1> from <ORG_1> and <PRICE_1> rent from my flat at <ADDRESS_1>, <ORG_2>, <LOCATION_1> <LOCATION_2>. I also have a home loan of <LOAN_1> with <ORG_3>.

Can you tell me how much tax I'll owe under the new regime?
```

### school-letter

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: none; left visible: Class 4B, roll no. 17
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Dear <PERSON_1>,

Your son <PERSON_2> (Class 4B, roll no. 17) was seen by the school counsellor today after an incident with another student. He mentioned he has been diagnosed with <SENSITIVE_ATTRIBUTE_1>.

Please call me at <CONTACT_1> or reply to <CONTACT_2>.

Regards,
<PERSON_3>, Principal
```

### flat-negotiation

- missed: Rahul
- partly covered: Flat 1102, Prestige Lakeside, Whitefield (90%)
- type mismatches: none
- optional masked: ₹1.75, Diwali; left visible: 1.7 final
- must stay readable: n/a
- extra masked: none
- contexts: none (expected NEGOTIATION)

```
<PERSON_1>: Bhai, the owner of <ADDRESS_1>, <ORG_1>, <LOCATION_1> is asking <PRICE_1>
<PERSON_1>: we offered <PRICE_2>, he said he'll go down to <PRICE_3> if we close by <DATE_1>
Me: ok tell him <PRICE_4> final, token amount <AMOUNT_1> by NEFT. My number for the agreement is <CONTACT_1>
Rahul: done, his name is <PERSON_2>, PAN on the sale deed will be <ID_1>
```

### gst-invoice

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: ICICI Bank; left visible: INV-2026-0912
- must stay readable: n/a
- extra masked: October
- contexts: none (expected none)

```
Tax Invoice #INV-2026-0912
Vendor: <ORG_1>, GSTIN <ID_1>, <ADDRESS_1>
Bill to: <ORG_2>, GSTIN <ID_2>

Freight charges for <DATE_1>: <AMOUNT_1> + 18% GST = <AMOUNT_2>.
Pay to: <ORG_3> A/c <ID_3>, IFSC <ID_4>.
Contact: <CONTACT_1> / <PERSON_1>, <CONTACT_2>
```

