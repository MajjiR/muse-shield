# Eval: glimmer · accounts/rohan-majji/models/muse-shield-glimmer-lora-v2-full#accounts/rohan-majji/deployments/ms-chat-v2full

n=951 · 123.91s · cost $0.2754 (gpu_time) · tokens in/out 756333/81387 · latency p50 2062 ms, p95 3450 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 97% / 99% / 98% |
| amount role accuracy | 70% |
| context precision / recall | 77% / 60% |
| context kind accuracy | 89% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 100% | 100% | 100% |
| CONTACT | 100% | 100% | 100% |
| DATE | 74% | 97% | 84% |
| ID | 100% | 100% | 100% |
| LOCATION | 90% | 82% | 86% |
| ORG | 99% | 99% | 99% |
| PERSON | 100% | 99% | 100% |
| SENSITIVE_ATTRIBUTE | 79% | 63% | 70% |

| template | entity F1 |
|---|---|
| admin | 98% |
| ecommerce | 99% |
| healthcare | 96% |
| ma_legal | 98% |
