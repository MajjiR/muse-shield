# Muse Shield eval results

Every eval run, newest first. Each row links to its folder: manifest (code version, git commit, settings, dataset hash), full reports, raw predictions, comparison table and charts (`report.html`).

Total recorded eval spend: **$3.87** (token cost for API models; run time x GPU rate for on-demand deployments, excluding idle time between runs).

Benchmark data: [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII), CC BY 4.0.

| run | eval | tag | model | docs | leak ↓ | core leak ↓ | recall ↑ | precision ↑ | valid JSON | cost |
|---|---|---|---|---|---|---|---|---|---|---|
| [20261103-221827_v0.0.1+5287585_full500-spark-contributor-low](nemotron-pii/20261103-221827_v0.0.1+5287585_full500-spark-contributor-low/report.html) | nemotron-pii | full500-spark-contributor-low | muse_spark `muse-spark-1.3-contributor` | 500 | 15.8% | 14.0% | 83.0% | 86.5% | 100.0% | $0.61 |
| [20261103-220750_v0.0.1+imported_full500-glimmer-base](nemotron-pii/20261103-220750_v0.0.1+imported_full500-glimmer-base/report.html) | nemotron-pii | full500-glimmer-base | glimmer `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ljrd6tyj` | 500 | 21.1% | 17.5% | 77.6% | 89.1% | 97.3% | $0.79 GPU |
| [20261103-220341_v0.0.1+imported_smoke5-reasoning-low](nemotron-pii/20261103-220341_v0.0.1+imported_smoke5-reasoning-low/report.html) | nemotron-pii | smoke5-reasoning-low | glimmer `accounts/fireworks/models/muse-glimmer-30b#accounts/rohan-majji/deployments/ljrd6tyj` | 5 | 22.5% | 17.4% | 71.0% | 75.9% | 92.0% | $0.07 GPU |
| [20261103-220341_v0.0.1+imported_smoke5-reasoning-low](nemotron-pii/20261103-220341_v0.0.1+imported_smoke5-reasoning-low/report.html) | nemotron-pii | smoke5-reasoning-low | muse_spark `muse-spark-1.3` | 5 | 9.9% | 7.6% | 85.5% | 89.6% | 100.0% | $0.22 |
| [20261103-220341_v0.0.1+imported_smoke5-reasoning-low](nemotron-pii/20261103-220341_v0.0.1+imported_smoke5-reasoning-low/report.html) | nemotron-pii | smoke5-reasoning-low | muse_wonder `muse-wonder-1.0` | 5 | 12.2% | 6.5% | 80.6% | 76.5% | 100.0% | $0.49 |
| [20261103-215654_v0.0.1+imported_smoke5-before-fixes](nemotron-pii/20261103-215654_v0.0.1+imported_smoke5-before-fixes/report.html) | nemotron-pii | smoke5-before-fixes | glimmer `accounts/fireworks/models/muse-glimmer-30b` | 5 | 100.0% | 100.0% | 0.0% | – | – | – |
| [20261103-215654_v0.0.1+imported_smoke5-before-fixes](nemotron-pii/20261103-215654_v0.0.1+imported_smoke5-before-fixes/report.html) | nemotron-pii | smoke5-before-fixes | muse_spark `muse-spark-1.3` | 5 | 95.8% | 95.5% | 4.8% | 100.0% | 42.0% | $0.39 |
| [20261103-215654_v0.0.1+imported_smoke5-before-fixes](nemotron-pii/20261103-215654_v0.0.1+imported_smoke5-before-fixes/report.html) | nemotron-pii | smoke5-before-fixes | muse_wonder `muse-wonder-1.0` | 5 | 40.4% | 36.5% | 61.3% | 95.0% | 86.0% | $1.31 |
