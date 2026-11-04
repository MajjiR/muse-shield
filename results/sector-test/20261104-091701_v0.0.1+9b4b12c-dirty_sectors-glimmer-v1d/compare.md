# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v1d#accounts/rohan-majji/deployments/ms-eval-v1d

n=951 · 128.0s · cost $0.2844 (gpu_time) · tokens in/out 756333/80144 · latency p50 2085 ms, p95 3745 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 54% / 72% / 62% |
| amount role accuracy | 76% |
| context precision / recall | 61% / 8% |
| context kind accuracy | 67% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 94% | 94% | 94% |
| AMOUNT | 99% | 76% | 86% |
| CONTACT | 99% | 100% | 99% |
| DATE | 64% | 98% | 77% |
| ID | 99% | 99% | 99% |
| LOCATION | 19% | 82% | 31% |
| ORG | 100% | 97% | 99% |
| PERSON | 26% | 40% | 31% |
| SECRET | 0% | 100% | 0% |
| SENSITIVE_ATTRIBUTE | 0% | 2% | 1% |

| template | entity F1 |
|---|---|
| admin | 68% |
| ecommerce | 68% |
| healthcare | 57% |
| ma_legal | 67% |
