# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3d-s250 (ours) | **16.9%** | 81.2% | 100% | 22s |

## Leak rate by category

| Category | Muse Glimmer + er-v3d-s250 (ours) |
|---|---|
| financial and corporate info | 13.7% (n=95) |
| healthcare information | 28.6% (n=28) |
| job, visa, and other applications | 16.5% (n=91) |
| quoted emails and messages | 17.6% (n=17) |
