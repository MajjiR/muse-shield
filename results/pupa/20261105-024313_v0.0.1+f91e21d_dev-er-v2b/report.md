# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v2b (ours) | **40.3%** | 46.5% | 100% | 29s |

## Leak rate by category

| Category | Muse Glimmer + er-v2b (ours) |
|---|---|
| financial and corporate info | 28.4% (n=95) |
| healthcare information | 53.6% (n=28) |
| job, visa, and other applications | 50.5% (n=91) |
| quoted emails and messages | 29.4% (n=17) |
