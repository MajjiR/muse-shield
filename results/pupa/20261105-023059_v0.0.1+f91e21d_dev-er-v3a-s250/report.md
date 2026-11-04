# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3a-s250 (ours) | **7.4%** | 87.1% | 100% | 26s |

## Leak rate by category

| Category | Muse Glimmer + er-v3a-s250 (ours) |
|---|---|
| financial and corporate info | 6.3% (n=95) |
| healthcare information | 14.3% (n=28) |
| job, visa, and other applications | 5.5% (n=91) |
| quoted emails and messages | 11.8% (n=17) |
