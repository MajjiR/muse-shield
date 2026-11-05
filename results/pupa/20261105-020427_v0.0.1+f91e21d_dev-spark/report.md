# PUPA: private details from real chatbot prompts that would reach the cloud model

101 English prompts (seed 7, ≤3000 chars) from PUPA (Columbia-NLP/PUPA, MIT; real WildChat
prompts). Units already replaced by WildChat's Presidio placeholders are skipped. Lower is better.

| Model | Leak rate | Prompts fully protected | Valid | Time |
|---|---|---|---|---|
| Muse Spark | **6.1%** | 89.1% | 100% | 33s |

## Leak rate by category

| Category | Muse Spark |
|---|---|
| financial and corporate info | 5.3% (n=95) |
| healthcare information | 3.6% (n=28) |
| job, visa, and other applications | 5.5% (n=91) |
| quoted emails and messages | 17.6% (n=17) |
