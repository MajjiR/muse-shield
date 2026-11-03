# Image masking · muse-spark-1.3 + sam-3.1

- values masked: 55.6% · leaked (incl. re-scan): 47.2% · harmless text over-masked: 6.2%
- ID photos blurred: 0/1 · re-scan ok: 2/5 · p50 22.4 s per image · Spark $0.0846 + 14 SAM requests

| image | masked | leaked | over-masked | re-scan | s |
|---|---|---|---|---|---|
| id-card | 6/7 | 14/08/1992 | << | ok | 22.8 |
| chat-screenshot | 2/8 | Vikram Sethi, Vikram, ₹48,500, vikram.sethi@okaxis, 4111 1111 1111 1111, 731, 22 Hill Road, Bandra West, Mumbai | deposit | FAIL | 25.1 |
| invoice | 5/10 | ₹1,00,000, ₹18,000, ₹1,18,000, 50100483920117, HDFC0000521 | Pay to account | FAIL | 22.4 |
| terminal-env | 0/4 | 10.20.3.11, Lumen#Prod2026, lmn_tok_8f3c21a9e7d4, nisha.pillai@lumen.dev | – | FAIL | 19.7 |
| clinic-note | 7/7 | – | – | ok | 17.7 |
| bus.jpg (photo) | faces 3/3 | | | ok | 15.7 |
| zidane.jpg (photo) | faces 2/2 | | | ok | 10.4 |
