# Image masking · muse-spark-1.3 + sam-3.1

- values masked: 97.2% · leaked (incl. re-scan): 2.8% · harmless text over-masked: 10.4%
- ID photos blurred: 1/1 · re-scan ok: 5/5 · p50 28.5 s per image · Spark $0.1531 + 14 SAM requests

| image | masked | leaked | over-masked | re-scan | s |
|---|---|---|---|---|---|
| id-card | 7/7 | – | << | ok | 29.1 |
| chat-screenshot | 8/8 | – | deposit | ok | 23.2 |
| invoice | 10/10 | – | Amount, Pay to account | ok | 29.8 |
| terminal-env | 3/4 | Lumen#Prod2026 | – | ok | 22.8 |
| clinic-note | 7/7 | – | Also: | ok | 28.5 |
| bus.jpg (photo) | faces 3/3 | | | ok | 17.5 |
| zidane.jpg (photo) | faces 2/2 | | | ok | 10.0 |
