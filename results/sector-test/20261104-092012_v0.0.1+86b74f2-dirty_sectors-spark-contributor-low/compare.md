# Eval: muse_spark · muse-spark-1.3-contributor

n=951 · 594.29s · cost $0.2743 (tokens) · tokens in/out 742068/1293813 · latency p50 11991 ms, p95 19223 ms

| metric | value |
|---|---|
| valid JSON (after retry) | 100% |
| valid JSON first try | 100% |
| entity precision / recall / F1 | 98% / 99% / 99% |
| amount role accuracy | 89% |
| context precision / recall | 73% / 93% |
| context kind accuracy | 97% |
| hallucinated spans (dropped) | 0 |

| entity type | P | R | F1 |
|---|---|---|---|
| ADDRESS | 100% | 100% | 100% |
| AMOUNT | 100% | 100% | 100% |
| CONTACT | 100% | 100% | 100% |
| DATE | 96% | 93% | 94% |
| ID | 100% | 100% | 100% |
| LOCATION | 33% | 82% | 47% |
| ORG | 100% | 100% | 100% |
| PERSON | 99% | 99% | 99% |
| SENSITIVE_ATTRIBUTE | 77% | 86% | 81% |

| template | entity F1 |
|---|---|
| admin | 99% |
| ecommerce | 100% |
| healthcare | 97% |
| ma_legal | 100% |
