# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3a-s750 (ours) | **14.7%** | 82.2% | 99% | 164s |

## Leak rate by category

| Category | Muse Glimmer + er-v3a-s750 (ours) |
|---|---|
| financial and corporate info | 11.6% (n=95) |
| healthcare information | 28.6% (n=28) |
| job, visa, and other applications | 14.3% (n=91) |
| quoted emails and messages | 11.8% (n=17) |
