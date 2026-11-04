# Entity resolution: v2 results

Base Glimmer and Spark use the v2 prompt (amount roles defined, worked example). er-v1 was scored with the v1 prompt;
er-v2a/er-v2b with the v2 prompt without the worked example (as trained). Test and challenge sets are the v1 sets, unchanged.

## test

| Metric | Base Glimmer | Muse Spark (low) | er-v1 | er-v2a | **er-v2b** |
|---|---|---|---|---|---|
| Valid JSON | 80.7% | 100.0% | 100.0% | 100.0% | 100.0% |
| Core leak | 24.7% | 0.6% | 0.2% | 0.2% | 0.1% |
| Coreference F1 | 0.567 | 0.891 | 0.969 | 0.978 | 0.979 |
| People resolved to one ID | 60.4% | 83.2% | 95.6% | 96.5% | 97.3% |
| Owner accuracy | 73.5% | 96.5% | 99.8% | 98.7% | 99.5% |
| UNKNOWN owners right | — | — | — | — | — |
| Amount role accuracy | 74.6% | 99.1% | 100.0% | 100.0% | 100.0% |
| Relation F1 | 0.460 | 0.843 | 0.987 | 0.980 | 0.983 |

## challenge

| Metric | Base Glimmer | Muse Spark (low) | er-v1 | er-v2a | **er-v2b** |
|---|---|---|---|---|---|
| Valid JSON | 93.8% | 100.0% | 100.0% | 100.0% | 100.0% |
| Core leak | 10.9% | 0.4% | 0.3% | 0.1% | 0.3% |
| Coreference F1 | 0.633 | 0.855 | 0.961 | 0.964 | 0.968 |
| People resolved to one ID | 61.8% | 72.4% | 95.1% | 95.4% | 93.1% |
| Owner accuracy | 91.0% | 95.9% | 96.3% | 96.8% | 98.5% |
| UNKNOWN owners right | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Amount role accuracy | 86.6% | 98.8% | 72.0% | 98.8% | 97.6% |
| Relation F1 | 0.745 | 0.919 | 0.729 | 0.998 | 0.998 |

## ambiguity

| Metric | Base Glimmer | Muse Spark (low) | er-v1 | er-v2a | **er-v2b** |
|---|---|---|---|---|---|
| Valid JSON | — | 100.0% | — | 100.0% | 100.0% |
| Core leak | — | 0.5% | — | 0.3% | 0.2% |
| Coreference F1 | — | 0.886 | — | 0.972 | 0.976 |
| People resolved to one ID | — | 78.9% | — | 93.9% | 95.8% |
| Owner accuracy | — | 94.5% | — | 98.2% | 99.5% |
| UNKNOWN owners right | — | 83.0% | — | 98.1% | 96.2% |
| Amount role accuracy | — | 82.5% | — | 100.0% | 100.0% |
| Relation F1 | — | 0.846 | — | 0.978 | 0.983 |

## TAB, real court judgments (127), people only

| Metric | Base Glimmer | Muse Spark (low) | er-v2a | **er-v2b** |
|---|---|---|---|---|
| Person leak | 84.9% | 2.9% | 7.1% | 3.3% |
| Coreference F1 | 0.083 | 0.815 | 0.758 | 0.854 |
| People resolved to one ID | 13.5% | 80.5% | 73.9% | 79.5% |

All TAB entity types (organisations included): coreference F1 Base Glimmer 0.024, Muse Spark (low) 0.749, er-v2a 0.386, **er-v2b** 0.548.
