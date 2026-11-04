# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v2-full#accounts/rohan-majji/deployments/ms-eval-v2full

n=60 · 8.55s · cost $0.0190 (gpu_time) · tokens in/out 45232/5050 · latency p50 2008 ms, p95 2770 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 100% / 100% / 100% |
| amount role accuracy | 100% |
| context precision / recall | 100% / 100% |
| context kind accuracy | 100% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 100% | 100% | 100% |
| LOCATION | 100% | 100% | 100% |
| ORG | 100% | 100% | 100% |
| PERSON | 100% | 100% | 100% |
| PROJECT | 100% | 100% | 100% |

| template | entity F1 |
|---|---|
| acceptance | 100% |
| deal | 100% |
| hr | 100% |
| loan | 100% |
| negative | 100% |
| negotiation | 100% |
| plan | 100% |
| price | 100% |
| project | 100% |
| salary_decision | 100% |
