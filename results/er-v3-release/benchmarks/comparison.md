| Benchmark | Metric | **Muse Glimmer + er-v3 (ours, local)** | Muse Spark, same instructions | Muse Spark, its own prompt | Muse Glimmer base | er-v2b (previous) |
|---|---|---|---|---|---|---|
| Nemotron-PII test (500 docs) | core leak ↓ | **2.0%** | 1.9% | 14.0% | 5.6% | 25.4% |
|  | leak, all types ↓ | **9.5%** | 9.0% | 15.8% | 11.7% | 31.3% |
| PUPA held-out (269 real prompts) | details leaked ↓ | **13.4%** | 13.4% | 7.9% | 43.3% | — |
|  | prompts fully protected ↑ | **86.2%** | 81.8% | 86.2% | 62.1% | — |
| TAB (127 ECHR judgments) | direct identifiers protected (ER_di) ↑ | **98.9%** | 82.6% | — | 39.7% | 49.8% |
|  | quasi identifiers protected (ER_qi) ↑ | **77.2%** | 81.5% | — | 25.8% | 57.1% |
|  | precision ↑ | **85.1%** | 77.7% | — | 77.5% | 97.9% |
| ER test (synthetic, 150) | core leak ↓ | **0.1%** | 0.6% | — | 24.7% | 0.1% |
|  | coreference F1 ↑ | **0.974** | 0.891 | — | 0.567 | 0.979 |
|  | owner accuracy ↑ | **99.5%** | 96.5% | — | 73.5% | 99.5% |
| Challenge (unseen doc types, 80) | coreference F1 ↑ | **0.958** | 0.855 | — | 0.633 | 0.968 |
| Ambiguity (80) | UNKNOWN owners right ↑ | **96.2%** | 83.0% | — | 37.7% | 96.2% |
