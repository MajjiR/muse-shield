# Image masking · muse-spark-1.3 + sam-3.1

- values masked: 94.4% · leaked (incl. re-scan): 5.6% · harmless text over-masked: 4.2%
- ID photos blurred: 0/1 · re-scan ok: 4/5 · p50 19.8 s per image · Spark $0.1445 + 14 SAM requests

| image | masked | leaked | over-masked | re-scan | s |
|---|---|---|---|---|---|
| id-card | 7/7 | – | << | ok | 28.2 |
| chat-screenshot | 8/8 | – | – | ok | 19.8 |
| invoice | 9/10 | ₹18,000 | Pay to account | ok | 28.0 |
| terminal-env | 4/4 | – | – | ok | 17.8 |
| clinic-note | 6/7 | Type 2 diabetes | – | FAIL | 18.9 |
| bus.jpg (photo) | faces 3/3 | | | ok | 16.8 |
| zidane.jpg (photo) | faces 2/2 | | | ok | 8.1 |
