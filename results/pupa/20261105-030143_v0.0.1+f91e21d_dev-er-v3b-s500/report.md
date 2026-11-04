# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3b-s500 (ours) | **17.7%** | 80.2% | 100% | 29s |

## Leak rate by category

| Category | Muse Glimmer + er-v3b-s500 (ours) |
|---|---|
| financial and corporate info | 17.9% (n=95) |
| healthcare information | 0.0% (n=28) |
| job, visa, and other applications | 22.0% (n=91) |
| quoted emails and messages | 23.5% (n=17) |
