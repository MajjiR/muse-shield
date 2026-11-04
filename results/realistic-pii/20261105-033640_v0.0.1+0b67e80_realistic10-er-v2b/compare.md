# Realistic PII loop · 10 examples × 2 rounds

model `accounts/rohan-majji/models/muse-shield-glimmer-er-v2b#accounts/rohan-majji/deployments/ms-er-cmp-er-v2b-1105-0331` (reasoning None) · 138.4s · $0.0000

**Missed 8 of 154 must-mask values (5.2% leak).** Valid analysis 100.0%.

| type | recall | misses |
|---|---|---|
| ADDRESS | 100.0% | 0 |
| AMOUNT | 100.0% | 0 |
| CONTACT | 92.3% | 2 |
| DATE | 100.0% | 0 |
| ID | 88.2% | 4 |
| ORG | 100.0% | 0 |
| PERSON | 100.0% | 0 |
| SECRET | 80.0% | 2 |
| SENSITIVE_ATTRIBUTE | 100.0% | 0 |

## Values missed (times out of rounds)

- `card-support-chat` · **312** · 2/2
- `travel-booking` · **QX7HT2** · 2/2
- `incident-secrets` · **203.0.113.45** · 2/2
- `incident-secrets` · **db-prod-3.internal.acme.dev** · 2/2

## Per example (last round)

### hr-transfer

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 1 December; left visible: Pune, HDFC Bank
- must stay readable: n/a
- extra masked: none
- contexts: none (expected HR)

```
Hi <PERSON_1>,

Following our call, I'm confirming that <PERSON_2> (Employee ID <ID_1>) will move to the Pune office from <DATE_1>. His revised CTC is <SALARY_1>.

Please update his bank details: HDFC Bank, account <ID_2>, IFSC <ID_3>. His PAN is <ID_4>.

Keep this confidential until the reorg is announced.

Thanks,
<PERSON_3>
HR Business Partner, <ORG_1>
```

### medical-intake

- missed: none
- partly covered: mild hypertension (71%)
- type mismatches: none
- optional masked: none; left visible: metformin 500 mg, Star Health
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Patient: <PERSON_1>, DOB <DATE_1>, MRN <ID_1>.
Address: <ADDRESS_1>. Phone: <CONTACT_1>.

Presenting with <SENSITIVE_ATTRIBUTE_1> and mild <SENSITIVE_ATTRIBUTE_2>. Currently on metformin 500 mg twice daily.

Insurance: Star Health policy <ID_2>. Emergency contact: her husband <PERSON_2>, <CONTACT_2>.
```

### card-support-chat

- missed: 312
- partly covered: none
- type mismatches: none
- optional masked: ₹1,299, Swiggy; left visible: 09/27
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
[10:42] Customer: hi my card got blocked, number is <ID_1>, expiry 09/27, cvv 312
[10:43] Agent (<PERSON_1>): Hi! Can you confirm your registered mobile and the last transaction?
[10:44] Customer: <CONTACT_1>, i paid <AMOUNT_1> to <ORG_1> yesterday. my UPI is <CONTACT_2>
[10:45] Customer: also my netbanking password is <SECRET_1> if that helps
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

- missed: QX7HT2
- partly covered: none
- type mismatches: none
- optional masked: 2031-05-19, 12 Dec 2026, 23 Old Airport Road; left visible: LH 761, 4421, The Leela Palace Bengaluru
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Booking ref: QX7HT2
Passenger: Mr. <PERSON_1>
Passport: <ID_1> (Nigeria), expires <DATE_1>
Flight: LH 761 Frankfurt to Bengaluru, <DATE_2>, seat 14C

Hotel: The Leela Palace Bengaluru, <ADDRESS_1>. Paid with Visa ending 4421.
Contact: <CONTACT_1>, <CONTACT_2>
```

### incident-secrets

- missed: 203.0.113.45, db-prod-3.internal.acme.dev
- partly covered: none
- type mismatches: none
- optional masked: acme-prod-backups; left visible: INC-4471, 2 Nov
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Incident INC-4471: production outage on 2 Nov

Root cause: a leaked AWS key <SECRET_1> was used from IP 203.0.113.45 to delete the S3 bucket <ORG_1>.

The on-call engineer, <PERSON_1> (<CONTACT_1>), rotated the key. Our Stripe secret <SECRET_2> was also in the same .env file and has been revoked.

Database host: db-prod-3.internal.<ORG_1>, user admin, password <SECRET_3>.
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

Last year I earned <SALARY_1> from <ORG_1> and <PRICE_1> rent from my flat at <ADDRESS_1>. I also have a home loan of <LOAN_1> with <ORG_2>.

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

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: ₹1.75; left visible: 1.7 final, Diwali
- must stay readable: n/a
- extra masked: none
- contexts: none (expected NEGOTIATION)

```
<PERSON_1>: Bhai, the owner of <ADDRESS_1> is asking <PRICE_1>
<PERSON_1>: we offered <PRICE_2>, he said he'll go down to <PRICE_3> if we close by Diwali
Me: ok tell him <PRICE_4> final, token amount <FEE_1> by NEFT. My number for the agreement is <CONTACT_1>
<PERSON_1>: done, his name is <PERSON_2>, PAN on the sale deed will be <ID_1>
```

### gst-invoice

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: none; left visible: INV-2026-0912, ICICI Bank
- must stay readable: n/a
- extra masked: none
- contexts: none (expected none)

```
Tax Invoice #INV-2026-0912
Vendor: <ORG_1>, GSTIN <ID_1>, <ADDRESS_1>
Bill to: <ORG_2>, GSTIN <ID_2>

Freight charges for October: <AMOUNT_1> + 18% GST = <AMOUNT_2>.
Pay to: ICICI Bank A/c <ID_3>, IFSC <ID_4>.
Contact: <CONTACT_1> / <PERSON_1>, <CONTACT_2>
```

