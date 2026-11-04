"""Export the TAB test split (real ECHR cases, human-annotated, MIT) as a PII benchmark in span format.

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/export_tab.py   # needs pandas + pyarrow (SSD venv)

The first annotator per document is used. Mentions marked DIRECT or QUASI identifiers are scored when
their type is one our policy masks: PERSON, CODE -> ID, DATETIME -> DATE, ORG, LOC -> LOCATION.
DEM (nationality etc.), QUANTITY, MISC and NO_MASK mentions are left out. TAB is never used for training.
"""

import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

URL = "https://huggingface.co/api/datasets/ildpil/text-anonymization-benchmark/parquet/default/test/0.parquet"
SRC = Path("/Volumes/MajjiR/ai/datasets/tab/test.parquet")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/eval/pii/tab-test.jsonl")
TYPE = {"PERSON": "PERSON", "CODE": "ID", "DATETIME": "DATE", "ORG": "ORG", "LOC": "LOCATION"}

if not SRC.exists():
    SRC.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(URL, SRC)
rows, seen = [], set()
for r in pd.read_parquet(SRC).itertuples():
    if r.doc_id in seen:
        continue
    seen.add(r.doc_id)
    spans = [{"start": int(m["start_offset"]), "end": int(m["end_offset"]), "text": m["span_text"], "label": TYPE[m["entity_type"]]}
             for m in r.entity_mentions if m["identifier_type"] in ("DIRECT", "QUASI") and m["entity_type"] in TYPE]
    rows.append({"uid": r.doc_id, "text": r.text, "domain": "echr", "locale": "", "format": "", "spans": spans})
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows))
print(f"{len(rows)} docs, {sum(len(x['spans']) for x in rows)} spans -> {OUT}")
