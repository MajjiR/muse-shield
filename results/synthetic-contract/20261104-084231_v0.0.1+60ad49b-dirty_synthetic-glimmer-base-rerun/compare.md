# Eval: glimmer · accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/skpptmp8

n=60 · 4.09s · cost $0.0091 (gpu_time) · tokens in/out 45232/5056 · latency p50 1044 ms, p95 1461 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 91% / 97% / 94% |
| amount role accuracy | 98% |
| context precision / recall | 78% / 74% |
| context kind accuracy | 79% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 92% | 92% | 92% |
| DATE | 0% | 100% | 0% |
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
| negotiation | 86% |
| plan | 83% |
| price | 100% |
| project | 88% |
| salary_decision | 95% |
