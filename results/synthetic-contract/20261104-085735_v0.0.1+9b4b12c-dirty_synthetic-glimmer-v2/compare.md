# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v2#accounts/rohan-majji/deployments/ms-eval-v2

n=60 · 9.51s · cost $0.0211 (gpu_time) · tokens in/out 45232/5290 · latency p50 2227 ms, p95 2946 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 100% / 100% / 100% |
| amount role accuracy | 100% |
| context precision / recall | 88% / 100% |
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
