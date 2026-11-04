# Labeller bake-off

Part A: 60 Nemotron-PII train documents (labels by construction). Part B: 50 held-out sector documents with code-planted values.

| labeller | leak ↓ | core leak ↓ | span recall | precision | valid JSON | planted missed ↓ | reasoning tokens/call | cost |
|---|---|---|---|---|---|---|---|---|
| spark-low (`muse-spark-1.3-contributor:low`) | 21.7% | 19.3% | 79.6% | 83.0% | – | 0/313 (0.0%) | 0 | $0.061 |
| deepseek-pro (`azure:DeepSeek-V4-Pro`) | 43.3% | 41.5% | 59.4% | 81.3% | – | 0/308 (0.0%) | 0 | $0.277 |
| deepseek-flash (`azure:DeepSeek-V4-Flash`) | 40.9% | 40.0% | 55.0% | 88.8% | – | 0/313 (0.0%) | 0 | $0.079 |

## Shared misses on Nemotron core spans

Gold (non-quasi) spans missed by one labeller, and how many of those the other also missed. A high share means a second opinion from that labeller adds little.

| A missed | n | also missed by B | share |
|---|---|---|---|
| spark-low → deepseek-pro | 87 | 51 | 59% |
| spark-low → deepseek-flash | 87 | 41 | 47% |
| deepseek-pro → spark-low | 189 | 51 | 27% |
| deepseek-pro → deepseek-flash | 189 | 95 | 50% |
| deepseek-flash → spark-low | 215 | 41 | 19% |
| deepseek-flash → deepseek-pro | 215 | 95 | 44% |

Core gold spans: 489; missed by every labeller: 30 (6.1%).

**spark-low** recall by type: ADDRESS 100%, CONTACT 97%, DATE 23%, ID 83%, LOCATION 77%, ORG 100%, PERSON 100%, SECRET 80%, SENSITIVE_ATTRIBUTE 39%
planted values missed (examples): []

**deepseek-pro** recall by type: ADDRESS 67%, CONTACT 66%, DATE 36%, ID 72%, LOCATION 70%, ORG 44%, PERSON 72%, SECRET 57%, SENSITIVE_ATTRIBUTE 23%
planted values missed (examples): []

**deepseek-flash** recall by type: ADDRESS 100%, CONTACT 66%, DATE 42%, ID 58%, LOCATION 61%, ORG 46%, PERSON 45%, SECRET 66%, SENSITIVE_ATTRIBUTE 39%
planted values missed (examples): []
