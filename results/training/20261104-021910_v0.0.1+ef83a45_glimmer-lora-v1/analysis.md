# glimmer-lora-v1: training health and data consistency (checked at step 30 of ~295)

## Training log
- No NaN/inf losses and no spikes (none >4 robust SD above the median).
- Loss by 10-step block: 0.050 ± 0.016 → 0.023 ± 0.008 → 0.027 ± 0.020. **Plateau from about step 15**, with
  more variance between batches afterwards.
- Raw gradient norm is **rising** (mean 694 in the first 10 steps → 971 in the last 10, max 2,320). Every
  update is clipped to norm 1.0.
- Reading: a rising raw gradient norm with a flat loss means the updates are clipped hard, not converging.
  That's consistent with a learning rate (1e-4) that's too high for this data.
- Pace: median 37.5 s/step (max 70 s); about 166 min left at step 30.
- **Overfitting:** none detectable, and none possible inside a single epoch. Every step is unseen data, so the
  training loss is effectively a held-out loss. It becomes a risk with more epochs, or through template
  memorization of the synthetic rows (8 templates, 609 rows).

## Data consistency (mix-v1 train, 4,759 rows)
| check | result | verdict |
|---|---|---|
| Same text labelled with >1 type | 4 of 5,946 strings (e.g. "Christian" religion vs name, "Jordan" place vs name) | genuine ambiguity, negligible |
| Structured PII left unlabelled (Nemotron) | email 2 of 561, URL 0 of 490, phone-like 17 of 1,567 (mostly IDs, not phones) | ~99% consistent; the regex layer covers the gaps |
| **DATE policy conflict** | **340 of 586 synthetic rows** contain dates ("March", "next quarter", "tomorrow") left unlabelled, while Nemotron labels DATE in 943 rows | **real conflict**: the model is taught both "label dates" and "don't" |
| **Quasi-identifier noise** (Nemotron) | words labelled in some rows and not others: 132 occurrences ("manager" 17 labelled / 13 not, "contractor", "Volunteer", "terminated", "Director", "language"…) | **real label noise** in SENSITIVE_ATTRIBUTE |

## Changes for v2 (current run continues unchanged: no divergence, and it is the v1 baseline)
1. **Learning rate 1e-4 → 5e-5** with warmup, batch 16 → 32 (less noisy updates). Re-check gradient norm and plateau.
2. **Hold-out checks during training**, not only before and after. Needed before trying more than 1 epoch.
3. **One DATE policy for both sources.** Synthetic rows label explicit dates the way Nemotron does, or both
   exclude vague relative dates. Decide before building mix-v2.
4. **Make the quasi-identifier labels consistent.** Relabel occupation / employment / education / language
   with one teacher pass, or drop those four labels from targets (scored separately anyway as quasi leak).
5. **Reduce synthetic template memorization.** Keep the synthetic share at ≤10% until the context data
   (teacher-labelled, varied) replaces the 9 templates.
