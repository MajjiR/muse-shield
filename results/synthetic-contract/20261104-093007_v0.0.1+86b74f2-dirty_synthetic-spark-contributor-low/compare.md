# Eval: muse_spark · muse-spark-1.3-contributor

n=60 · 43.82s · cost $0.0157 (tokens) · tokens in/out 44332/74601 · latency p50 10957 ms, p95 16246 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 94% / 96% / 95% |
| amount role accuracy | 98% |
| context precision / recall | 54% / 79% |
| context kind accuracy | 79% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 62% | 62% | 62% |
| AMOUNT | 94% | 94% | 94% |
| LOCATION | 81% | 100% | 90% |
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
| negotiation | 90% |
| plan | 100% |
| price | 100% |
| project | 100% |
| salary_decision | 77% |
