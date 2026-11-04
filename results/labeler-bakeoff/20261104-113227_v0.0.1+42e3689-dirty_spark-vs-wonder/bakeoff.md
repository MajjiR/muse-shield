# Labeller bake-off

Part A: 60 Nemotron-PII train documents (labels by construction). Part B: 50 held-out sector documents with code-planted values.

| labeller | leak ↓ | core leak ↓ | span recall | precision | valid JSON | planted missed ↓ | reasoning tokens/call | cost |
|---|---|---|---|---|---|---|---|---|
| spark-low (`muse-spark-1.3-contributor:low`) | 21.2% | 18.8% | 81.4% | 84.4% | 100.0% | 0/313 (0.0%) | 879 | $0.154 |
| spark-medium (`muse-spark-1.3-contributor:medium`) | 20.9% | 18.5% | 80.6% | 82.0% | 100.0% | 0/313 (0.0%) | 1440 | $0.244 |
| wonder-low (`muse-wonder-1.0:low`) | 15.6% | 13.1% | 85.1% | 83.4% | 100.0% | 0/313 (0.0%) | 269 | $5.780 |

## Shared misses on Nemotron core spans

Gold (non-quasi) spans missed by one labeller, and how many of those the other also missed. A high share means a second opinion from that labeller adds little.

| A missed | n | also missed by B | share |
|---|---|---|---|
| spark-low → spark-medium | 78 | 67 | 86% |
| spark-low → wonder-low | 78 | 46 | 59% |
| spark-medium → spark-low | 82 | 67 | 82% |
| spark-medium → wonder-low | 82 | 50 | 61% |
| wonder-low → spark-low | 59 | 46 | 78% |
| wonder-low → spark-medium | 59 | 50 | 85% |

Core gold spans: 489; missed by every labeller: 46 (9.4%).

**spark-low** recall by type: ADDRESS 100%, CONTACT 96%, DATE 28%, ID 82%, LOCATION 89%, ORG 100%, PERSON 100%, SECRET 77%, SENSITIVE_ATTRIBUTE 45%
planted values missed (examples): []

**spark-medium** recall by type: ADDRESS 100%, CONTACT 96%, DATE 23%, ID 86%, LOCATION 89%, ORG 100%, PERSON 100%, SECRET 71%, SENSITIVE_ATTRIBUTE 32%
planted values missed (examples): []

**wonder-low** recall by type: ADDRESS 100%, CONTACT 95%, DATE 38%, ID 97%, LOCATION 93%, ORG 100%, PERSON 100%, SECRET 83%, SENSITIVE_ATTRIBUTE 23%
planted values missed (examples): []
