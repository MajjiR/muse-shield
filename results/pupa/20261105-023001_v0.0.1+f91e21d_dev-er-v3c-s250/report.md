# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3c-s250 (ours) | **19.9%** | 68.3% | 100% | 14s |

## Leak rate by category

| Category | Muse Glimmer + er-v3c-s250 (ours) |
|---|---|
| financial and corporate info | 16.8% (n=95) |
| healthcare information | 17.9% (n=28) |
| job, visa, and other applications | 24.2% (n=91) |
| quoted emails and messages | 17.6% (n=17) |
