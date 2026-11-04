# Muse Shield training and test data (fictional / public only)

| path | what | made by |
|---|---|---|
| `synth-v2/train/` | 5,093 labelled paragraphs from 1,600 documents (400 each: M&A/legal, healthcare, e-commerce, admin) | `python -m muse_shield.synth scale` |
| `synth-v2/test/` | 951 labelled paragraphs from 300 held-out documents (75 per sector), never used in training | same run, split by document before labelling |
| `quasi-relabel-v2.jsonl` | Spark's job title / employment / education / language spans for 4,400 Nemotron training paragraphs | `python -m muse_shield.relabel` |

Every document is fictional. Code generates each document's identity pack (names, +91 phones, emails,
Aadhaar/PAN/IFSC-style IDs, accounts, addresses, dates, amounts). Muse Spark 1.3 (Contributor mode, medium
reasoning) writes the document, and two independent labelling passes (low and medium effort) keep only the
labels both agree on. A paragraph is dropped if any planted identifier is left unlabelled (`dropped.jsonl`
records why). `rows.jsonl` is in the runtime chat format, and `rows.manifest.jsonl` says, row by row, which
sector, document and split each row comes from.

`runs/train/mix-v2/` (not committed) is rebuilt deterministically from these files plus Nemotron-PII:
`python -m muse_shield.trainset --v2 --test-sample <benchmark docs> --out runs/train/mix-v2`.
