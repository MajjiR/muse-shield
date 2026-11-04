# er-v3 checkpoints (core leak; coreference F1 for the synthetic sets)

PUPA dev = 101 prompts from the PUPA test half, never used for the final score (pupa-final, 269 prompts).
Nemotron held-out = 150 Nemotron *train* docs not trained on; the 500 test docs are untouched.

| run | step | ER test | challenge | ambiguity (UNKNOWN) | v3 val | Nemotron held-out | PUPA dev leak | verdict |
|---|---|---|---|---|---|---|---|---|
| er-v2b | — | 0.1% / 0.979 | 0.3% / 0.968 | 0.2% (96%) | — | — | — | baseline |
| Muse Spark | — | — | — | — | — | — | 6.1% | baseline |
| C | 250 | 0.2% / 0.957 | 0.1% / 0.946 | 0.6% (98.1%) | 0.1% | 0.7% | 19.9% | STOP? below er-v2b on test coref_f1 0.957 (bar 0.97); challenge coref_f1 0.946 (bar 0.96); ambiguity core_leak 0.006 (bar 0.005) |
| D | 250 | 0.2% / 0.966 | 0.2% / 0.952 | 0.3% (83.0%) | 0.3% | 1.4% | 16.9% | STOP? below er-v2b on test coref_f1 0.966 (bar 0.97); test owner 0.972 (bar 0.99); challenge coref_f1 0.952 (bar 0.96); ambiguity unknown 0.830 (bar 0.95) |
| A | 250 | 0.1% / 0.974 | 0.4% / 0.958 | 0.2% (96.2%) | 0.3% | 0.3% | 7.4% | continue (watch: challenge coref_f1 0.958 (bar 0.96)) |
| B | 250 | 0.7% / 0.977 | 0.4% / 0.968 | 0.1% (98.1%) | 0.1% | 4.8% | 12.6% | continue (watch: test core_leak 0.007 (bar 0.005)) |
| C | 500 | 0.2% / 0.967 | 0.1% / 0.955 | 0.1% (96.2%) | 0.0% | 0.9% | 9.5% | continue (watch: test coref_f1 0.967 (bar 0.97); challenge coref_f1 0.955 (bar 0.96)) |
| A | 500 | 1.5% / 0.964 | 0.6% / 0.952 | 2.6% (100.0%) | 0.3% | 1.9% | 16.9% | STOP? below er-v2b on test core_leak 0.015 (bar 0.005); test coref_f1 0.964 (bar 0.97); test owner 0.964 (bar 0.99); challenge core_leak 0.006 (bar 0.005); challenge coref_f1 0.952 (bar 0.96); ambiguity core_leak 0.026 (bar 0.005) |
| B | 500 | 0.1% / 0.980 | 0.2% / 0.969 | 0.2% (100.0%) | 0.1% | 1.9% | 17.7% | continue (watch: test owner 0.983 (bar 0.99)) |
| B | 510 | 0.0% / 0.980 | 0.3% / 0.968 | 0.1% (100.0%) | 0.1% | 3.6% | 23.8% | STOP? no gain since last checkpoint on PUPA dev, Nemotron held-out or v3 val |
| C | 750 | 0.1% / 0.979 | 0.3% / 0.970 | 0.1% (98.1%) | 0.1% | 0.9% | 14.7% | STOP? no gain since last checkpoint on PUPA dev, Nemotron held-out or v3 val |
| A | 750 | 0.0% / 0.978 | 0.1% / 0.963 | 0.1% (100.0%) | 0.0% | 0.7% | 14.7% | continue |
| A | 760 | 0.1% / 0.979 | 0.4% / 0.959 | 0.1% (100.0%) | 0.0% | 0.7% | 16.0% | STOP? no gain since last checkpoint on PUPA dev, Nemotron held-out or v3 val |
| C | 804 | 0.1% / 0.975 | 0.1% / 0.974 | 0.1% (100.0%) | 0.3% | 0.7% | 13.0% | continue |
