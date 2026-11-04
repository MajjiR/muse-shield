# Multi-turn chat test: entity-resolution Glimmer in the real UI

**Setup:**
- **App:** `feature/entity-resolution-chat` on localhost:8772, driven through the real UI with Claude in Chrome.
- **Masking (call 1):** Glimmer 30B + `muse-shield-glimmer-er-v2a`.
- **Replies (call 2):** cloud Muse Spark 1.3, a dev stand-in.
- **Data:** made-up people only.

Each turn's exact sent text, spans, replies and vault edges are in `conversations.json`.

| # | Conversation | Turns | Identity across turns | Owners and relations | Consent | Issues |
|---|---|---|---|---|---|---|
| 1 | HR reimbursement reply → note to Rahul | 2 | ✅ "Rahul", "Nikhil" kept `<PERSON_2>`, `<PERSON_3>`; "Kavya" = "Kavya Menon" | ✅ amount, employee ID, account and IFSC → Nikhil | — | ⚠️ "account ending 4471" and "Pune" not masked |
| 2 | Manager note to HR → Slack to Priya | 2 | ✅ "Priya", "Arjun" kept their labels; "Arjun" = "Arjun Bose" | ✅ bonus → Priya; Siddharth MANAGES both | — | Turn 1 became a `send_email` tool call (waits for confirmation). Turn 2 was sent twice, a test-harness slip |
| 3 | Bank dispute letter → "is the card valid / Visa or Mastercard?" | 2 | ✅ | ✅ card, account, phone → Fatima; Imran SPOUSE_OF Fatima | ✅ asked for `<ID_1>`; **declined**, so it explained how to check yourself | ⚠️ "Card xx8823" (last 4 digits) and merchant "GLOBALTECH STORE DUBAI" not masked; ❌ Fatima EMPLOYED_BY Axis Bank (should be a customer) |
| 4 | Cardiology referral → SMS to "her son" | 2 | ✅ "her son" → `<PERSON_3>` (Ramesh) in Spark's reply | ✅ age, MRN, condition, weight → Kamala; phone → Ramesh; Kamala PARENT_OF Ramesh; doctor TREATS Kamala | — | ⚠️ "BP 158/94", "amlodipine" and the symptoms not masked |
| 5 | M&A board update → "what revenue multiple?" | 2 | ✅ "Kestrel" = "Kestrel Pharma" | ✅ deal value → Meridian, revenue → Kestrel | ✅ after the fix: asked for `<DEAL_VALUE_1>`, then `<REVENUE_1>`; **shared** both; answer "~5.61x" | ❌ before the fix, a mid-line NEED_CONTEXT wasn't recognised (fixed: `chat.py` regex, plus a test) |
| 6 | Welcome email → note to Manish about Sneha | 2 | ✅ "Manish", "Sneha" kept `<PERSON_2>`, `<PERSON_1>` | ✅ salary, address, start date → Sneha; Manish MANAGES Sneha | — | — |

**What works:**
- **Identity:** one placeholder per person, across turns and across name forms.
- **Owners and relations:** correct in 5 of 6 conversations.
- **Consent:** the request-then-continue flow works on both Allow and Deny, including two values asked for one after another.
- **No leaks of full names, emails, phone numbers or full IDs in any turn.**

**Fixes for the next model round** (training-data gaps, not app bugs):
1. **Partial identifiers:** "card xx8823", "account ending 4471". These are only partly hidden, so the last digits still go to Meta.
2. **Medical details beyond the diagnosis:** medications, vitals (BP), symptoms.
3. **All-caps merchant or organisation names** in statements.
4. **Customer and bank relation:** add CLIENT_OF examples, so a customer isn't labelled EMPLOYED_BY.
