# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Glimmer + er-v3b-s510 (ours) | **23.8%** | 74.3% | 98% | 29s |

## Leak rate by category

| Category | Muse Glimmer + er-v3b-s510 (ours) |
|---|---|
| financial and corporate info | 22.1% (n=95) |
| healthcare information | 7.1% (n=28) |
| job, visa, and other applications | 30.8% (n=91) |
| quoted emails and messages | 23.5% (n=17) |
