# Realistic conversations · 6 chats, 18 turns × 2 rounds

model `muse-spark-1.3` (reasoning minimal) · 327.1s · $0.1396

**Missed 2 of 292 must-mask values (0.7% leak).** Valid analysis 100.0%. Recurring values linked to one placeholder: 9.1%.

| sector | must | missed | extra masked | avg latency | cost |
|---|---|---|---|---|---|
| general | 38 | 0 | 2 | 8842 ms | $0.0204 |
| finance | 48 | 2 | 3 | 8476 ms | $0.0209 |
| healthcare | 42 | 0 | 10 | 7830 ms | $0.0210 |
| legal | 62 | 0 | 15 | 10847 ms | $0.0298 |
| hr | 60 | 0 | 11 | 10160 ms | $0.0265 |
| tech | 42 | 0 | 7 | 8354 ms | $0.0210 |

| type | recall | misses |
|---|---|---|
| ADDRESS | 100.0% | 0 |
| AMOUNT | 100.0% | 0 |
| CONTACT | 100.0% | 0 |
| DATE | 100.0% | 0 |
| ID | 100.0% | 0 |
| ORG | 100.0% | 0 |
| PERSON | 100.0% | 0 |
| SECRET | 100.0% | 0 |
| SENSITIVE_ATTRIBUTE | 90.0% | 2 |

## Values missed (times out of rounds)

- `finance-wealth-review/t2` · **treated for depression** · 2/2

## Linking: the same value across turns

- round 1 · `general-wedding-move` · **Shreya** → <PERSON_2>, <PERSON_6>, <PLAN_1> (SPLIT)
- round 1 · `finance-wealth-review` · **Rajiv** → <PERSON_1>, <PERSON_2>, <PLAN_1> (SPLIT)
- round 1 · `health-discharge` · **HIV** → <HR_1>, <SENSITIVE_ATTRIBUTE_14>, <SENSITIVE_ATTRIBUTE_5> (SPLIT)
- round 1 · `legal-settlement-nda` · **Chawla** → <NEGOTIATION_1>, <NEGOTIATION_2>, <PERSON_1>, <PERSON_5>, <PERSON_6> (SPLIT)
- round 1 · `legal-settlement-nda` · **Harish Vikrant** → <NEGOTIATION_1>, <NEGOTIATION_2>, <PERSON_2> (SPLIT)
- round 1 · `legal-settlement-nda` · **Pillai** → <NEGOTIATION_1>, <ORG_5>, <PERSON_3>, <PERSON_7> (SPLIT)
- round 1 · `hr-offer-complaint-layoffs` · **Ritesh** → <HR_2>, <HR_3>, <PERSON_4> (SPLIT)
- round 1 · `hr-offer-complaint-layoffs` · **Manoj** → <HR_2>, <PERSON_3> (SPLIT)
- round 1 · `tech-outage-breach-bridge` · **Apollo** → <NEGOTIATION_1>, <ORG_2>, <ORG_3> (SPLIT)
- round 1 · `tech-outage-breach-bridge` · **Siddharth** → <DECISION_1>, <PERSON_5> (SPLIT)
- round 1 · `tech-outage-breach-bridge` · **Nandini** → <PERSON_4> (ok)
- round 2 · `general-wedding-move` · **Shreya** → <PERSON_2>, <PERSON_6>, <PLAN_1> (SPLIT)
- round 2 · `finance-wealth-review` · **Rajiv** → <PERSON_1>, <PERSON_2>, <PLAN_1> (SPLIT)
- round 2 · `health-discharge` · **HIV** → <HR_1>, <SENSITIVE_ATTRIBUTE_4>, <SENSITIVE_ATTRIBUTE_6> (SPLIT)
- round 2 · `legal-settlement-nda` · **Chawla** → <NEGOTIATION_1>, <NEGOTIATION_2>, <NEGOTIATION_3>, <PERSON_1>, <PERSON_5>, <PERSON_6> (SPLIT)
- round 2 · `legal-settlement-nda` · **Harish Vikrant** → <DECISION_1>, <PERSON_2>, <PERSON_7> (SPLIT)
- round 2 · `legal-settlement-nda` · **Pillai** → <ORG_6>, <PERSON_3>, <PERSON_8> (SPLIT)
- round 2 · `hr-offer-complaint-layoffs` · **Ritesh** → <HR_2>, <HR_3>, <PERSON_4> (SPLIT)
- round 2 · `hr-offer-complaint-layoffs` · **Manoj** → <HR_2>, <PERSON_3> (SPLIT)
- round 2 · `tech-outage-breach-bridge` · **Apollo** → <DEAL_1>, <ORG_2>, <ORG_3> (SPLIT)
- round 2 · `tech-outage-breach-bridge` · **Siddharth** → <DECISION_1>, <PERSON_5> (SPLIT)
- round 2 · `tech-outage-breach-bridge` · **Nandini** → <PERSON_4> (ok)

## Per turn (last round)

### general-wedding-move/t1

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Suresh, 21 Feb 2027, Taj Fort Aguada, Goa, Kotak; left visible: none
- must stay readable: month-by-month plan with what to book first (kept)
- extra masked: none
- contexts: PLAN (expected none)

```
Hey, I need help planning the next 3 months. <PLAN_1> Can you make me a month-by-month plan with what to book first?
```

### general-wedding-move/t2

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Persistent Systems; left visible: none
- must stay readable: Is it normal to share Aadhaar with a landlord (kept)
- extra masked: none
- contexts: PLAN (expected none)

```
<PLAN_2> The landlord is <PERSON_5>, <CONTACT_1>, she wants a copy of my Aadhaar (<ID_2>) and my company ID letter from <ORG_2> for the police verification. Is it normal to share Aadhaar with a landlord? What should I black out?
```

### general-wedding-move/t3

- missed: none
- partly covered: rehab for alcohol addiction (63%)
- type mismatches: none
- optional masked: August; left visible: none
- must stay readable: no-alcohol, sugar-free table (kept)
- extra masked: Shreya's
- contexts: none (expected none)

```
One more thing, sensitive. <PERSON_6> brother <PERSON_7> has been in rehab for <SENSITIVE_ATTRIBUTE_1> since <DATE_2> and her parents don't want it mentioned at the wedding. He's also <SENSITIVE_ATTRIBUTE_2>. Can you help me write a note to the caterer (<PERSON_8> at <CONTACT_2>) asking for a no-alcohol, sugar-free table for a few guests without saying why? And remind me to repay the <LOAN_1> I borrowed from my friend <PERSON_9> before the wedding.
```

### finance-wealth-review/t1

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Zerodha, HDFC, Bajaj; left visible: 30 Sep, 9.1%
- must stay readable: flag concentration risk (kept)
- extra masked: none
- contexts: none (expected none)

```
I'm preparing the quarterly review for my client <PERSON_1> (PAN <ID_1>, client code <ID_2>). Portfolio as of 30 Sep: <AMOUNT_1> in equity MFs, <AMOUNT_2> in direct stocks (demat <ID_3> with <ORG_1>), <AMOUNT_3> FDs at <ORG_2>, and <AMOUNT_4> in a commercial property at <ADDRESS_1> that gives <REVENUE_1> rent. He has a <LOAN_1> loan against property with <ORG_3> at 9.1%. Summarize this into a one-page allocation view and flag concentration risk.
```

### finance-wealth-review/t2

- missed: treated for depression
- partly covered: none
- type mismatches: none
- optional masked: 15 Dec; left visible: going through a divorce
- must stay readable: what do I need to escalate to compliance (kept)
- extra masked: none
- contexts: PLAN (expected PLAN, DECISION)

```
Context you need: <PERSON_2> is going through a divorce. <PLAN_1> I told him I can't advise on hiding assets. He also mentioned he's being treated for <SENSITIVE_ATTRIBUTE_1> and doesn't want it in any file. What's the compliant way to document this conversation for our records, and what do I need to escalate to compliance?
```

### finance-wealth-review/t3

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 12 Jan, 2030; left visible: none
- must stay readable: Keep it warm but formal (MASKED)
- extra masked: divorce
- contexts: DECISION, PLAN (expected none)

```
Draft the email to him. His email is <CONTACT_1>, cc his CA <PERSON_5> (<CONTACT_2>). <PLAN_2> <DECISION_1>
```

### health-discharge/t1

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 28 Oct 2026, Kokilaben Hospital, 30 Oct, 3 Nov; left visible: tenofovir/lamivudine/dolutegravir, labetalol 100 mg, emergency C-section
- must stay readable: discharge summary (kept)
- extra masked: 34F
- contexts: none (expected none)

```
Help me write a discharge summary. Patient <PERSON_1>, <SENSITIVE_ATTRIBUTE_1>, DOB <DATE_1>, MRN <ID_1>, admitted <DATE_2> at <ORG_1> under Dr. <PERSON_2> (Reg. no. <ID_2>). Admitted with <SENSITIVE_ATTRIBUTE_2> at <SENSITIVE_ATTRIBUTE_3>, BP 160/110 on arrival. She is <SENSITIVE_ATTRIBUTE_4>, on tenofovir/lamivudine/dolutegravir, viral load undetectable. Managed with labetalol 100 mg BD and magnesium sulfate. Delivered a healthy baby girl by emergency C-section on <DATE_3>, 1.8 kg. Discharged <DATE_4> on labetalol 100 mg BD.
```

### health-discharge/t2

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Sion Hospital, JJ Hospital; left visible: 6 weeks
- must stay readable: draft a referral letter (kept)
- extra masked: nurse
- contexts: none (expected none)

```
Her follow-up: she lives at <ADDRESS_1>, phone <CONTACT_1>, husband <PERSON_3> (alternate contact <CONTACT_2>). She has no insurance; the bill of <FEE_1> was partly covered by the hospital's charity fund, balance <FEE_2> outstanding. Her sister <PERSON_4> is a <SENSITIVE_ATTRIBUTE_5> at <ORG_2> and will help with home BP monitoring. Please also draft a referral letter to <PERSON_5>, ART centre at <ORG_3> (<CONTACT_3>) for the infant's PCR test at 6 weeks.
```

### health-discharge/t3

- missed: none
- partly covered: none
- type mismatches: fatima.s92 ID→CONTACT
- optional masked: Pali Hill, housekeeper; left visible: none
- must stay readable: Can I legally leave it out of the fit-to-work certificate (kept)
- extra masked: none
- contexts: HR (expected none)

```
<HR_1> Can I legally leave it out of the fit-to-work certificate? What should the certificate say instead? Also her login for the hospital portal is <CONTACT_4> / <SECRET_1>, can you tell her how to change it, she's not tech savvy.
```

### legal-settlement-nda/t1

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Desai & Partners, Bombay High Court, 29 Oct, Axis Bank, Worli PS; left visible: none
- must stay readable: first draft of a settlement agreement (kept)
- extra masked: Advocate, MD, Vikrant, associate, ex-CFO
- contexts: NEGOTIATION (expected DEAL, NEGOTIATION)

```
I'm an <SENSITIVE_ATTRIBUTE_1> at <ORG_1>. Need a first draft of a settlement agreement. Matter: <ORG_2> v. <PERSON_1>, Commercial Suit No. <ID_1>, <ORG_3>. Our client <ORG_4> (<SENSITIVE_ATTRIBUTE_2>: <PERSON_2>) sued their <SENSITIVE_ATTRIBUTE_3> <PERSON_1> for diverting <AMOUNT_1> to a shell company, <ORG_5>. Opposing counsel is <SENSITIVE_ATTRIBUTE_4> <PERSON_3> of <ORG_6>. <NEGOTIATION_1>
```

### legal-settlement-nda/t2

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Kotak, Lokhandwala, dentist; left visible: none
- must stay readable: Give me a negotiation plan (kept)
- extra masked: tomorrow
- contexts: DECISION, NEGOTIATION (expected NEGOTIATION, DECISION)

```
<NEGOTIATION_2> <NEGOTIATION_3> <NEGOTIATION_4> <DECISION_1> Give me a negotiation plan for the call with <PERSON_8> <DATE_2>.
```

### legal-settlement-nda/t3

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Singapore, 2 years; left visible: none
- must stay readable: Standard mutual NDA (kept)
- extra masked: CEO, Mumbai
- contexts: DEAL (expected DEAL)

```
Separately draft an NDA for a new client: <ORG_10> (CIN <ID_5>), signatory <PERSON_9>, <SENSITIVE_ATTRIBUTE_6>, <CONTACT_1>, <CONTACT_2>, registered office at <ADDRESS_2>. <DEAL_1> Standard mutual NDA, nothing fancy.
```

### hr-offer-complaint-layoffs/t1

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: Mu Sigma, AuthBridge, cheque bounce case, March; left visible: none
- must stay readable: Draft the offer letter (kept)
- extra masked: Bengaluru, Senior Data Engineer
- contexts: HR (expected HR, DECISION)

```
I'm the hiring manager for the <SENSITIVE_ATTRIBUTE_1> role at <ORG_1>. <HR_1> Draft the offer letter and tell me how to handle the pregnancy and the background flag legally.
```

### hr-offer-complaint-layoffs/t2

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 27 Oct, Q3, Dec; left visible: none
- must stay readable: What are my obligations as his skip-level (kept)
- extra masked: none
- contexts: HR (expected HR)

```
Different issue, confidential. <HR_2> <HR_3> Manoj's personal email is <CONTACT_3> and he's asked that HR not use his office email. What are my obligations as his skip-level, and what should I NOT do or say?
```

### hr-offer-complaint-layoffs/t3

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 31 Dec, Feb, H-1B, 58 years old, low performer; left visible: none
- must stay readable: fair selection framework (kept)
- extra masked: India, US, US office
- contexts: HR (expected HR, PLAN, DECISION)

```
<HR_4> Give me a fair selection framework and tell me which of these picks are legally risky in <LOCATION_3> and the <LOCATION_4>.
```

### tech-outage-breach-bridge/t1

- missed: none
- partly covered: none
- type mismatches: 10.20.3.11 ID→CONTACT
- optional masked: 31 Mar, Sunday, Friday, 02:14 IST, db-primary.lumio.internal, lumio_app; left visible: none
- must stay readable: customer-facing RCA (kept)
- extra masked: CTO, SRE
- contexts: DEAL, PLAN, PROJECT (expected DEAL)

```
I'm <SENSITIVE_ATTRIBUTE_1> at <ORG_1> (Series A, 40 people). <DEAL_1> <PLAN_1> <PROJECT_1> The postmortem Slack thread has the connection string in it: <SECRET_1>. Write me a customer-facing RCA that's honest but doesn't name the engineer.
```

### tech-outage-breach-bridge/t2

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: lumio-ml-scratch, Apollo; left visible: July
- must stay readable: do we have to notify CERT-In (MASKED)
- extra masked: CERT-In
- contexts: none (expected none)

```
While fixing it we found worse: a Jupyter notebook in the repo with hardcoded creds. AWS <SECRET_2> / <SECRET_3>, a Twilio token <SECRET_4>, and a Razorpay key <SECRET_5>. Also patient records from <ORG_3> (names + Aadhaar) were in an S3 bucket <ID_1> set to public-read since July. Our DPO is <PERSON_3> (<CONTACT_4>). Under DPDP Act do we have to notify <ORG_4> and the patients, and in what timeline? Draft the internal incident note.
```

### tech-outage-breach-bridge/t3

- missed: none
- partly covered: none
- type mismatches: none
- optional masked: 20 Dec; left visible: none
- must stay readable: 5-line message (kept)
- extra masked: CEO
- contexts: DEAL, DECISION (expected DEAL, DECISION)

```
Investor side, strictly confidential: our lead, <PERSON_4> at <ORG_5>, knows about the outage but not the bucket. <DEAL_2> <DECISION_1> I think that's a disclosure problem. Help me write a 5-line message to Siddharth making the case, and a separate neutral update for Nandini if he agrees.
```

