# Eval: glimmer · accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/skpptmp8

n=951 · 115.91s · cost $0.2576 (gpu_time) · tokens in/out 794609/169069 · latency p50 904 ms, p95 7128 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 95% |
| valid JSON first try | 95% |
| entity precision / recall / F1 | 91% / 94% / 93% |
| amount role accuracy | 73% |
| context precision / recall | 61% / 38% |
| context kind accuracy | 74% |
| hallucinated spans (dropped) | 2 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 98% | 98% | 98% |
| CONTACT | 99% | 100% | 100% |
| DATE | 67% | 97% | 79% |
| ID | 86% | 86% | 86% |
| LOCATION | 75% | 82% | 78% |
| ORG | 83% | 98% | 90% |
| PERSON | 94% | 94% | 94% |
| PROJECT | 0% | 100% | 0% |
| SENSITIVE_ATTRIBUTE | 77% | 16% | 26% |

| template | entity F1 |
|---|---|
| admin | 95% |
| ecommerce | 96% |
| healthcare | 85% |
| ma_legal | 93% |
