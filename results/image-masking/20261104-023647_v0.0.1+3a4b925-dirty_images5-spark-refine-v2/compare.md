# Image masking · muse-spark-1.3 + sam-3.1

- values masked: 100.0% · leaked (incl. re-scan): 0.0% · harmless text over-masked: 4.2%
- ID photos blurred: 1/1 · re-scan ok: 5/5 · p50 25.0 s per image · Spark $0.1518 + 14 SAM requests

| image | masked | leaked | over-masked | re-scan | s |
|---|---|---|---|---|---|
| id-card | 7/7 | – | << | ok | 28.2 |
| chat-screenshot | 8/8 | – | – | ok | 22.6 |
| invoice | 10/10 | – | Pay to account | ok | 30.0 |
| terminal-env | 4/4 | – | – | ok | 25.0 |
| clinic-note | 7/7 | – | – | ok | 21.7 |
| bus.jpg (photo) | faces 3/3 | | | ok | 15.9 |
| zidane.jpg (photo) | faces 2/2 | | | ok | 8.8 |
