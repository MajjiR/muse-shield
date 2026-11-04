# Image masking · muse-spark-1.3 + sam-3.1

- values masked: 88.9% · leaked (incl. re-scan): 11.1% · harmless text over-masked: 2.1%
- ID photos blurred: 1/1 · re-scan ok: 4/5 · p50 25.8 s per image · Spark $0.1590 + 14 SAM requests

| image | masked | leaked | over-masked | re-scan | s |
|---|---|---|---|---|---|
| id-card | 7/7 | – | – | ok | 25.8 |
| chat-screenshot | 8/8 | – | – | ok | 27.4 |
| invoice | 9/10 | ₹18,000 | Pay to account | ok | 34.7 |
| terminal-env | 4/4 | – | – | ok | 25.8 |
| clinic-note | 4/7 | +91 90044 18273, Type 2 diabetes, Kavita Menon | – | FAIL | 23.3 |
| bus.jpg (photo) | faces 3/3 | | | ok | 15.7 |
| zidane.jpg (photo) | faces 2/2 | | | ok | 9.2 |
