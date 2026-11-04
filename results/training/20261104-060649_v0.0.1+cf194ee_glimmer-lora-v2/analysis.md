# glimmer-lora-v2: early stop at step 450 of 588

- **Data:** mix-v2, 9,406 train / 290 val rows: Nemotron with specific dates only and the
  quasi relabel as a union, plus Spark sector rows and template rows. Settings are the same as
  v1c (lr 1e-4, batch 16, rank 8).
- **Held-out loss before training:** 0.0828.
- **Smoothed training loss:** fell from 0.052 (steps 0–50) to about 0.030 (steps 250–450).
- **Stop:** the smoothed loss then improved by less than 2% in two consecutive 75-step windows,
  so the supervisor stopped at step 450 and promoted that checkpoint as
  `muse-shield-glimmer-lora-v2`.
- **Time:** 40.5 min of training in 1 attempt, with no crashes. Cost $0 (promotion).

## Caveat: the stop was decided on training loss only
The cookbook recipe scores the held-out set only before training and at the end of the epoch,
so this run has no held-out loss after step 0. Training loss on mix-v2 is noisy because the
mix holds rows of very different difficulty: Nemotron paragraphs, Spark sector documents and
short template rows. Per-step loss ranged from 0.003 to 0.056 in the last 150 steps. A
training-loss plateau in a mix like this is weak evidence of convergence.

**Action taken:** `glimmer-lora-v2-full` resumes from the step-450 checkpoint at the same data
position and finishes the epoch with early stop off, so it gets an end-of-epoch held-out loss
comparable with v1c's 0.0122. Both models are kept. Tomorrow's evals decide between them on
the Nemotron 500, the synthetic contract eval and the sector test set.

**Pipeline follow-up:** base plateau stops on held-out loss, e.g. score a fixed validation
subset every N steps from the supervisor, or raise the window for mixed datasets.
