# TAB anonymisation metrics: our fine-tuned Glimmer vs Muse Spark

Text Anonymization Benchmark (Pilán et al., 2022): ECHR court judgments, test split, every annotator. First
~6,000 characters per judgment. Scored from saved predictions (no model calls), `scripts/tab_official.py`.

| Metric | Muse Glimmer + er-v3a (ours) | Muse Spark (same instructions) | Base Muse Glimmer (same instructions) | Muse Glimmer + er-v2b (previous) |
|---|---|---|---|---|
| Direct identifiers protected (ER_di) | 98.9% | 82.6% | 39.7% | 49.8% |
| Quasi identifiers protected (ER_qi) | 77.2% | 81.5% | 25.8% | 57.1% |
| Identifier words masked (token recall) | 80.4% | 82.8% | 27.0% | 62.1% |
| Masked words that needed it (precision) | 85.1% | 77.7% | 77.5% | 97.9% |
| Valid outputs | 126/127 | 127/127 | 48/127 | 127/127 |

Entities counted: Muse Glimmer + er-v3a (ours): direct 1152, quasi 13740

## Recall by identifier and entity type

| Type | Muse Glimmer + er-v3a (ours) | Muse Spark (same instructions) | Base Muse Glimmer (same instructions) | Muse Glimmer + er-v2b (previous) |
|---|---|---|---|---|
| DIRECT:CODE (n=568) | 99.8% | 66.0% | 35.0% | 0.0% |
| DIRECT:PERSON (n=575) | 98.4% | 99.1% | 44.2% | 98.8% |
| QUASI:CODE (n=1004) | 48.9% | 51.6% | 0.8% | 0.5% |
| QUASI:DATETIME (n=7067) | 86.5% | 89.9% | 28.9% | 71.6% |
| QUASI:DEM (n=644) | 23.8% | 48.0% | 7.5% | 6.1% |
| QUASI:LOC (n=977) | 87.6% | 94.7% | 40.1% | 2.1% |
| QUASI:MISC (n=309) | 4.2% | 12.6% | 2.9% | 4.2% |
| QUASI:ORG (n=919) | 53.6% | 63.9% | 27.4% | 21.4% |
| QUASI:PERSON (n=2347) | 94.8% | 92.5% | 31.9% | 96.6% |
| QUASI:QUANTITY (n=473) | 56.4% | 61.9% | 10.6% | 52.9% |
