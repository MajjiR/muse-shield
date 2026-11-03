# Eval: glimmer · accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ljrd6tyj

n=60 · 341.82s · cost $0.7596 (gpu_time) · tokens in/out 45232/5147 · latency p50 2979 ms, p95 299002 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 90% / 97% / 94% |
| amount role accuracy | 98% |
| context precision / recall | 76% / 76% |
| context kind accuracy | 80% |
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
| plan | 80% |
| price | 100% |
| project | 88% |
| salary_decision | 95% |
