# PUPA: private details from real chatbot prompts that would reach the cloud model

120 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat prompts). Units
WildChat had already replaced with Presidio placeholders (any form) are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v2b (ours) | **44.4%** | 49.1% | 100% | 29s |
| Muse Glimmer + v2 (ours, PII + context) | **24.1%** | 69.3% | 100% | 14s |
| Muse Spark | **5.4%** | 90.4% | 100% | 31s |

## Leak rate by category

| Category | Muse Glimmer + er-v2b (ours) | Muse Glimmer + v2 (ours, PII + context) | Muse Spark |
|---|---|---|---|
| financial and corporate info | 41.2% (n=80) | 35.0% (n=80) | 3.8% (n=80) |
| healthcare information | 25.9% (n=27) | 18.5% (n=27) | 3.7% (n=27) |
| job, visa, and other applications | 55.4% (n=112) | 17.9% (n=112) | 8.0% (n=112) |
| quoted emails and messages | 22.7% (n=22) | 22.7% (n=22) | 0.0% (n=22) |
