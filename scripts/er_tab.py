"""Build the real-text coreference check from TAB (European Court of Human Rights judgments, human-annotated).

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_tab.py   # -> runs/er/tab/tab.docs.jsonl

TAB links every mention of the same person or organisation with an entity_id, which is exactly a
coreference cluster. We keep the first ~6,000 characters of each judgment (cut at a paragraph break),
one annotator per document, and these mentions: PERSON and ORG (all), CODE (as ID; direct or quasi
identifiers only). TAB doesn't annotate pronouns, so score with --relaxed and read coreference and
people-resolved, not mention precision. Dates, places and demographics follow a different policy than ours.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SRC = Path("/Volumes/MajjiR/ai/datasets/tab/test.parquet")
TYPES = {"PERSON": "PERSON", "ORG": "ORG", "CODE": "ID"}


def main(limit_chars: int = 6000) -> int:
    df = pd.read_parquet(SRC)
    out, seen = [], set()
    for _, r in df.iterrows():
        if r.doc_id in seen:
            continue
        seen.add(r.doc_id)
        text = r.text
        cut = text.rfind("\n\n", 0, limit_chars)
        cut = cut if cut > 1000 else min(len(text), limit_chars)
        text = text[:cut]
        clusters: dict[str, dict] = {}
        no_mask: set[tuple[int, int]] = set()
        for m in r.entity_mentions:
            et = TYPES.get(m["entity_type"])
            if not et or m["end_offset"] > cut:
                continue
            if et == "ID" and m["identifier_type"] == "NO_MASK":
                continue
            c = clusters.setdefault(m["entity_id"], {"type": et, "mentions": []})
            c["mentions"].append((int(m["start_offset"]), int(m["end_offset"])))
            if m["identifier_type"] == "NO_MASK":  # in a cluster for coreference, but not a leak if left visible
                no_mask.add((int(m["start_offset"]), int(m["end_offset"])))
        ents, counts = [], {}
        for c in sorted(clusters.values(), key=lambda c: min(s for s, _ in c["mentions"])):
            counts[c["type"]] = counts.get(c["type"], 0) + 1
            ents.append({"id": f"{c['type']}_{counts[c['type']]}", "type": c["type"], "mentions": sorted(set(c["mentions"]))})
        out.append({"uid": r.doc_id, "family": "tab", "doc_type": "court judgment", "text": text, "entities": ents, "relations": [],
                    "no_mask": sorted(no_mask)})
    dst = REPO / "runs/er/tab"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "tab.docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in out))
    persons = sum(1 for d in out for e in d["entities"] if e["type"] == "PERSON")
    multi = sum(1 for d in out for e in d["entities"] if e["type"] == "PERSON" and len(e["mentions"]) > 1)
    print(f"{len(out)} documents, {persons} people ({multi} mentioned more than once), "
          f"{sum(len(e['mentions']) for d in out for e in d['entities'])} mentions -> {dst / 'tab.docs.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
