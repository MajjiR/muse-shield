# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + v2 (ours, PII + context) | **100.0%** | 0.0% | 0% | 5s |

## Leak rate by category

| Category | Muse Glimmer + v2 (ours, PII + context) |
|---|---|
| financial and corporate info | 100.0% (n=95) |
| healthcare information | 100.0% (n=28) |
| job, visa, and other applications | 100.0% (n=91) |
| quoted emails and messages | 100.0% (n=17) |
