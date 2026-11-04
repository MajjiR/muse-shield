# Eval: glimmer · accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ms-eval-base

n=951 · 127.55s · cost $0.2835 (gpu_time) · tokens in/out 797818/177452 · latency p50 986 ms, p95 16257 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 95% |
| valid JSON first try | 95% |
| entity precision / recall / F1 | 91% / 94% / 93% |
| amount role accuracy | 73% |
| context precision / recall | 61% / 39% |
| context kind accuracy | 75% |
| hallucinated spans (dropped) | 3 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 98% | 98% | 98% |
| CONTACT | 99% | 100% | 100% |
| DATE | 67% | 97% | 79% |
| ID | 86% | 86% | 86% |
| LOCATION | 82% | 82% | 82% |
| ORG | 83% | 98% | 90% |
| PERSON | 94% | 94% | 94% |
| PROJECT | 0% | 100% | 0% |
| SENSITIVE_ATTRIBUTE | 64% | 14% | 23% |

| template | entity F1 |
|---|---|
| admin | 95% |
| ecommerce | 96% |
| healthcare | 85% |
| ma_legal | 93% |
