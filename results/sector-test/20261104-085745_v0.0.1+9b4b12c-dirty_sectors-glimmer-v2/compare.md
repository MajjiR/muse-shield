# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v2#accounts/rohan-majji/deployments/ms-eval-v2

n=951 · 142.2s · cost $0.3160 (gpu_time) · tokens in/out 758265/91003 · latency p50 2364 ms, p95 3842 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 98% / 98% / 98% |
| amount role accuracy | 82% |
| context precision / recall | 61% / 78% |
| context kind accuracy | 87% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 99% | 99% |
| AMOUNT | 99% | 99% | 99% |
| CONTACT | 100% | 100% | 100% |
| DATE | 76% | 95% | 84% |
| ID | 100% | 100% | 100% |
| LOCATION | 100% | 82% | 90% |
| ORG | 100% | 99% | 99% |
| PERSON | 100% | 99% | 99% |
| SENSITIVE_ATTRIBUTE | 89% | 49% | 63% |

| template | entity F1 |
|---|---|
| admin | 99% |
| ecommerce | 99% |
| healthcare | 95% |
| ma_legal | 97% |
