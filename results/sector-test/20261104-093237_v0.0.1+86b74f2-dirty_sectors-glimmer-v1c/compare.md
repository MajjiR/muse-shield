# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v1c#accounts/rohan-majji/deployments/ms-eval-v1c-1104-0929

n=951 · 118.95s · cost $0.2643 (gpu_time) · tokens in/out 756333/76695 · latency p50 1914 ms, p95 3428 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 61% / 78% / 69% |
| amount role accuracy | 71% |
| context precision / recall | 50% / 2% |
| context kind accuracy | 53% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 99% | 84% | 91% |
| CONTACT | 100% | 100% | 100% |
| DATE | 63% | 98% | 77% |
| ID | 100% | 100% | 100% |
| LOCATION | 78% | 64% | 70% |
| ORG | 99% | 97% | 98% |
| PERSON | 39% | 54% | 45% |
| SENSITIVE_ATTRIBUTE | 1% | 3% | 1% |

| template | entity F1 |
|---|---|
| admin | 70% |
| ecommerce | 77% |
| healthcare | 63% |
| ma_legal | 73% |
