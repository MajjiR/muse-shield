# TAB anonymisation metrics: our fine-tuned Glimmer vs Muse Spark

Text Anonymization Benchmark (Pilán et al., 2022): ECHR court judgments, test split, every annotator. First
~6,000 characters per judgment. Scored from saved predictions (no model calls), `scripts/tab_official.py`.

| Metric | Muse Glimmer + er-v2b (ours) | Muse Spark | Base Muse Glimmer |
|---|---|---|---|
| Direct identifiers protected (ER_di) | 49.8% | 76.8% | 16.5% |
| Quasi identifiers protected (ER_qi) | 57.1% | 75.5% | 10.7% |
| Identifier words masked (token recall) | 62.1% | 79.3% | 11.4% |
| Masked words that needed it (precision) | 97.9% | 77.4% | 82.5% |
| Valid outputs | 127/127 | 127/127 | 18/127 |

Entities counted: Muse Glimmer + er-v2b (ours): direct 1152, quasi 13740

## Recall by identifier and entity type

| Type | Muse Glimmer + er-v2b (ours) | Muse Spark | Base Muse Glimmer |
|---|---|---|---|
| DIRECT:CODE (n=568) | 0.0% | 55.5% | 10.9% |
| DIRECT:PERSON (n=575) | 98.8% | 98.3% | 22.1% |
| QUASI:CODE (n=1004) | 0.5% | 3.5% | 0.1% |
| QUASI:DATETIME (n=7067) | 71.6% | 85.8% | 11.3% |
| QUASI:DEM (n=644) | 6.1% | 46.7% | 2.2% |
| QUASI:LOC (n=977) | 2.1% | 86.1% | 15.6% |
| QUASI:MISC (n=309) | 4.2% | 14.6% | 0.0% |
| QUASI:ORG (n=919) | 21.4% | 59.4% | 6.7% |
| QUASI:PERSON (n=2347) | 96.6% | 96.7% | 18.0% |
| QUASI:QUANTITY (n=473) | 52.9% | 59.0% | 2.5% |
