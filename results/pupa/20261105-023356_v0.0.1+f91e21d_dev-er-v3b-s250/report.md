# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3b-s250 (ours) | **12.6%** | 81.2% | 100% | 30s |

## Leak rate by category

| Category | Muse Glimmer + er-v3b-s250 (ours) |
|---|---|
| financial and corporate info | 11.6% (n=95) |
| healthcare information | 0.0% (n=28) |
| job, visa, and other applications | 16.5% (n=91) |
| quoted emails and messages | 17.6% (n=17) |
