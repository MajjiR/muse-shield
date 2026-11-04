# glimmer-lora-v2-full: v2 trained to the end of the epoch

This run continues `glimmer-lora-v2`, which early-stopped at step 450 on a training-loss
plateau. It resumed from `rohan-majji/run-84d1fe99…/step-450` with the same data cursor (7,200
of 9,406 examples consumed) and early stop off, and ran steps 451–588.

| | v2 (step 450) | v2-full (step 588) |
|---|---|---|
| model | `muse-shield-glimmer-lora-v2` | `muse-shield-glimmer-lora-v2-full` |
| training | 40.5 min | 40.5 + 29.2 min (incl. the ~6 min epoch-end eval) |
| held-out loss (mix-v2 val, 290 rows) | 0.0828 at step 0; none after | **0.0267** at step 588 |
| mean train loss, steps 400–499 → 500–588 | 0.0305 | 0.0292 |

- **Training loss in 100-step windows:** 0.0456, 0.0370, 0.0332, 0.0325, 0.0305, 0.0292. It kept
  improving slowly after step 450, so the plateau stop came slightly early.
- **The held-out losses are not comparable across versions.** v1c's 0.0122 was scored on
  mix-v1's val set. This run's 0.0267 was scored on mix-v2's, which is harder: Spark sector
  documents with roles and contexts, plus the added quasi-identifier labels. The step-0 losses
  were close (0.0845 vs 0.0828), but the targets differ. The model comparison has to come from
  task metrics on identical test sets: the Nemotron 500, the synthetic contract eval and
  data/synth-v2/test.
- **Bug found and fixed during this run (8f7e824):** the supervisor took the resumed-from run's
  ID as its own. It didn't affect this run, because the normal completion promotes through the
  recipe's own output, and no crash happened.
