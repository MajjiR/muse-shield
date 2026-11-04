# PUPA: private details from real chatbot prompts that would reach the cloud model

269 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3a (ours) | **13.4%** | 86.2% | 99% | 99s |
| Base Muse Glimmer (same instructions) | **43.3%** | 62.1% | 90% | 1312s |
| Muse Spark (same instructions) | **13.4%** | 81.8% | 100% | 213s |
| Muse Spark | **7.9%** | 86.2% | 100% | 136s |

## Leak rate by category

| Category | Muse Glimmer + er-v3a (ours) | Base Muse Glimmer (same instructions) | Muse Spark (same instructions) | Muse Spark |
|---|---|---|---|---|
| financial and corporate info | 16.9% (n=254) | 40.2% (n=254) | 16.5% (n=254) | 5.5% (n=254) |
| healthcare information | 20.7% (n=116) | 55.2% (n=116) | 8.6% (n=116) | 6.9% (n=116) |
| job, visa, and other applications | 7.7% (n=248) | 45.6% (n=248) | 12.5% (n=248) | 10.9% (n=248) |
| quoted emails and messages | 5.0% (n=40) | 15.0% (n=40) | 12.5% (n=40) | 7.5% (n=40) |
