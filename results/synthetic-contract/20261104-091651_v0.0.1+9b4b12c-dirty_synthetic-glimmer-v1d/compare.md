# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v1d#accounts/rohan-majji/deployments/ms-eval-v1d

n=60 · 9.4s · cost $0.0209 (gpu_time) · tokens in/out 45232/5122 · latency p50 2236 ms, p95 3291 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 92% / 96% / 94% |
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
| PERSON | 74% | 85% | 80% |
| PROJECT | 100% | 100% | 100% |

| template | entity F1 |
|---|---|
| acceptance | 100% |
| deal | 90% |
| hr | 91% |
| loan | 100% |
| negative | 100% |
| negotiation | 94% |
| plan | 100% |
| price | 80% |
| project | 100% |
| salary_decision | 100% |
