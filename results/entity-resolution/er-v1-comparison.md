# Entity resolution v1: base Glimmer vs Muse Spark vs fine-tuned Glimmer

### test (150 documents)

| Metric | Base Glimmer | Muse Spark (low) | **Glimmer + er-v1 LoRA** |
|---|---|---|---|
| Valid JSON | 73.3% | 100.0% | 100.0% |
| Leak (all names and values) | 31.7% | 0.5% | 0.2% |
| Core leak (PERSON, ID, CONTACT, SECRET, ADDRESS) | 32.1% | 0.4% | 0.2% |
| Mention F1 | 0.683 | 0.831 | 0.988 |
| Coreference F1 (pairwise links) | 0.513 | 0.898 | 0.969 |
| People resolved to exactly one ID | 52.4% | 84.1% | 95.6% |
| Owner accuracy | 66.8% | 97.2% | 99.8% |
| Type accuracy | 70.1% | 99.9% | 100.0% |
| Amount role accuracy | 64.9% | 100.0% | 100.0% |
| Relation F1 | 0.422 | 0.837 | 0.987 |

### challenge (80 documents)

| Metric | Base Glimmer | Muse Spark (low) | **Glimmer + er-v1 LoRA** |
|---|---|---|---|
| Valid JSON | 87.5% | 100.0% | 100.0% |
| Leak (all names and values) | 14.5% | 0.6% | 0.4% |
| Core leak (PERSON, ID, CONTACT, SECRET, ADDRESS) | 15.1% | 0.7% | 0.3% |
| Mention F1 | 0.785 | 0.826 | 0.980 |
| Coreference F1 (pairwise links) | 0.629 | 0.867 | 0.961 |
| People resolved to exactly one ID | 60.9% | 71.4% | 95.1% |
| Owner accuracy | 84.9% | 95.9% | 96.3% |
| Type accuracy | 87.8% | 99.9% | 99.1% |
| Amount role accuracy | 64.6% | 74.4% | 72.0% |
| Relation F1 | 0.731 | 0.912 | 0.729 |

Runs: `20261104-174217_v0.0.1+bccef46_base-glimmer`, `20261104-174216_v0.0.1+bccef46_spark-low`, `20261104-180945_v0.0.1+bccef46_er-v1`
