# Labeller bake-off

Part A: 60 Nemotron-PII train documents (labels by construction). Part B: 50 held-out sector documents with code-planted values.

| labeller | leak ↓ | core leak ↓ | span recall | precision | valid JSON | planted missed ↓ | reasoning tokens/call | cost |
|---|---|---|---|---|---|---|---|---|
| ds-pro-low (`deepseek:deepseek-v4-pro:low`) | 16.0% | 13.5% | 84.4% | 79.4% | 100.0% | 0/313 (0.0%) | 632 | $2.318 |
| ds-flash-low (`deepseek:deepseek-flash:low`) | 13.1% | 10.7% | 86.7% | 81.4% | 100.0% | 0/313 (0.0%) | 226 | $0.398 |

## Shared misses on Nemotron core spans

Gold (non-quasi) spans missed by one labeller, and how many of those the other also missed. A high share means a second opinion from that labeller adds little.

| A missed | n | also missed by B | share |
|---|---|---|---|
| ds-pro-low → ds-flash-low | 64 | 42 | 66% |
| ds-flash-low → ds-pro-low | 53 | 42 | 79% |

Core gold spans: 489; missed by every labeller: 42 (8.6%).

**ds-pro-low** recall by type: ADDRESS 100%, CONTACT 99%, DATE 34%, ID 91%, LOCATION 91%, ORG 100%, PERSON 100%, SECRET 83%, SENSITIVE_ATTRIBUTE 32%
planted values missed (examples): []

**ds-flash-low** recall by type: ADDRESS 100%, CONTACT 100%, DATE 32%, ID 95%, LOCATION 93%, ORG 98%, PERSON 100%, SECRET 86%, SENSITIVE_ATTRIBUTE 52%
planted values missed (examples): []
