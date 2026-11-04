"""TAB-style anonymisation metrics for saved entity-resolution predictions (no model calls).

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/tab_official.py

TAB (Pilán et al., 2022: "The Text Anonymization Benchmark") marks every mention in ECHR court judgments as a
DIRECT identifier, a QUASI identifier or NO_MASK, groups mentions of the same thing into entities, and has
several annotators per document. Its headline metrics, which this computes:

- ER_di / ER_qi: entity-level recall on direct / quasi identifiers. An entity counts as protected only if
  ALL of its (direct / quasi) mentions are masked.
- Token recall: share of the words inside direct and quasi mentions that are masked.
- Precision: share of masked words that some annotator marked as DIRECT or QUASI (unweighted; the official
  script also offers an information-content weighting, which needs a language model and isn't done here).

Each annotator is scored separately and the results pooled, as the official evaluation does. Our runs saw the
first ~6,000 characters of each judgment (cut at a paragraph break, as in scripts/er_tab.py), so only
mentions in that window count. A leading title ("Mr", "Judge") needn't be masked. Masked spans are the
predicted names and values; pronouns and descriptions ("he", "the applicant") are never masked by design.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield import resolution as R  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402

SRC = Path("/Volumes/MajjiR/ai/datasets/tab/test.parquet")
RUNS = {"Muse Glimmer + er-v2b (ours)": "er-v2b", "Muse Spark": "spark-low-v2prompt", "Base Muse Glimmer": "base-glimmer-v2prompt"}
TITLE = re.compile(r"(?:(?:Mr|Mrs|Ms|Mx|Dr|Prof|Judge|Justice|Lord|Lady|Sir|Dame)\.?\s+)+")
WORD = re.compile(r"\w+", re.UNICODE)


def cut_of(text: str, limit: int = 6000) -> int:
    cut = text.rfind("\n\n", 0, limit)
    return cut if cut > 1000 else min(len(text), limit)


def masked_chars(text: str, pred: dict | None) -> list[bool]:
    cov = [False] * len(text)
    for e in (pred or {}).get("entities", []):
        for s, t in e["mentions"]:
            if R.is_reference(text[s:t]) and e["type"] in ("PERSON", "ORG"):
                continue  # references stay readable by design
            for i in range(max(0, s), min(len(text), t)):
                cov[i] = True
    return cov


def mention_masked(text: str, cov: list[bool], s: int, e: int) -> bool:
    m = TITLE.match(text, s, e)
    s = m.end() if m and m.end() < e else s
    return all(cov[i] for i in range(s, e) if text[i].isalnum())


def score(run_dir: Path, docs: pd.DataFrame) -> dict:
    preds = {json.loads(l)["uid"]: json.loads(l) for l in (run_dir / "tab.preds.jsonl").read_text().splitlines()}
    ent = {"DIRECT": [0, 0], "QUASI": [0, 0]}
    by_type: dict[str, list[int]] = {}
    tok = [0, 0]  # words in direct/quasi mentions: masked, total
    prec = [0, 0]  # masked words: inside some annotator's direct/quasi mention, total
    valid = 0
    for doc_id, group in docs.groupby("doc_id"):
        text_full = group.iloc[0].text
        cut = cut_of(text_full)
        text = text_full[:cut]
        row = preds.get(doc_id)
        pred = row.get("pred") if row else None
        valid += pred is not None
        cov = masked_chars(text, pred)
        needed = [False] * len(text)  # union over annotators: chars some annotator wants masked
        for _, ann in group.iterrows():
            entities: dict[str, dict] = {}
            for m in ann.entity_mentions:
                s, e, kind = int(m["start_offset"]), int(m["end_offset"]), m["identifier_type"]
                if e > cut or kind == "NO_MASK":
                    continue
                for i in range(s, e):
                    needed[i] = True
                x = entities.setdefault((m["entity_id"], kind), {"type": m["entity_type"], "mentions": []})
                x["mentions"].append((s, e))
                for w in WORD.finditer(text, s, e):
                    tok[1] += 1
                    tok[0] += all(cov[w.start():w.end()])
            for (eid, kind), x in entities.items():
                ok = all(mention_masked(text, cov, s, e) for s, e in x["mentions"])
                ent[kind][0] += ok
                ent[kind][1] += 1
                t = by_type.setdefault(f"{kind}:{x['type']}", [0, 0])
                t[0] += ok
                t[1] += 1
        for w in WORD.finditer(text):
            if all(cov[w.start():w.end()]):
                prec[1] += 1
                prec[0] += any(needed[w.start():w.end()])
    r = lambda a: a[0] / a[1] if a[1] else None  # noqa: E731
    return {"docs": int(docs.doc_id.nunique()), "annotations": len(docs), "valid_outputs": valid,
            "ER_di": r(ent["DIRECT"]), "ER_qi": r(ent["QUASI"]), "token_recall": r(tok), "precision": r(prec),
            "counts": {"direct_entities": ent["DIRECT"], "quasi_entities": ent["QUASI"], "tokens": tok, "masked_words": prec},
            "by_type": {k: {"recall": v[0] / v[1], "n": v[1]} for k, v in sorted(by_type.items()) if v[1] >= 10}}


def svg_chart(rows: dict) -> str:
    metrics = [("ER_di", "Direct identifiers protected"), ("ER_qi", "Quasi identifiers protected"),
               ("token_recall", "Identifier words masked"), ("precision", "Masked words that needed it")]
    colors = ["#1f6f5c", "#4a5bdc", "#b9b9b9"]
    W, row_h, bar_h, left = 760, 74, 16, 230
    H = 60 + row_h * len(metrics) + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Inter, Helvetica, Arial, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           '<text x="20" y="30" font-size="17" font-weight="600" fill="#111">TAB: real court judgments, human-labelled (127 docs, all annotators)</text>']
    for k, name in enumerate(rows):
        out.append(f'<rect x="{20 + k * 230}" y="42" width="12" height="12" fill="{colors[k]}"/>'
                   f'<text x="{38 + k * 230}" y="53" font-size="12" fill="#333">{name}</text>')
    for i, (key, label) in enumerate(metrics):
        y0 = 80 + i * row_h
        out.append(f'<text x="20" y="{y0 + 22}" font-size="13" fill="#111">{label}</text>')
        for k, (name, res) in enumerate(rows.items()):
            v = res[key] or 0.0
            y = y0 + k * (bar_h + 4)
            w = (W - left - 70) * v
            out.append(f'<rect x="{left}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{colors[k]}" rx="2"/>'
                       f'<text x="{left + w + 6:.1f}" y="{y + 12}" font-size="12" fill="#333">{v * 100:.1f}%</text>')
    out.append(f'<text x="20" y="{H - 10}" font-size="11" fill="#777">First ~6,000 characters of each ECHR test judgment; '
               'entity counts as protected only if every mention is masked. Pilán et al. 2022.</text></svg>')
    return "\n".join(out)


def main() -> int:
    docs = pd.read_parquet(SRC)
    rows = {}
    for name, tag in RUNS.items():
        run = sorted((RESULTS / "entity-resolution").glob(f"*_{tag}"))[-1]
        rows[name] = score(run, docs) | {"run": run.name}
    started = time.time()
    out = RESULTS / "tab-official" / new_run_id("er-v2b-vs-spark", started, git_version())
    out.mkdir(parents=True, exist_ok=True)
    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = ["# TAB anonymisation metrics: our fine-tuned Glimmer vs Muse Spark", "",
             "Text Anonymization Benchmark (Pilán et al., 2022): ECHR court judgments, test split, every annotator. First",
             "~6,000 characters per judgment. Scored from saved predictions (no model calls), `scripts/tab_official.py`.", "",
             "| Metric | " + " | ".join(rows) + " |", "|---|" + "---|" * len(rows)]
    for key, label in [("ER_di", "Direct identifiers protected (ER_di)"), ("ER_qi", "Quasi identifiers protected (ER_qi)"),
                       ("token_recall", "Identifier words masked (token recall)"), ("precision", "Masked words that needed it (precision)")]:
        lines.append(f"| {label} | " + " | ".join(pct(r[key]) for r in rows.values()) + " |")
    lines.append("| Valid outputs | " + " | ".join(f"{r['valid_outputs']}/{r['docs']}" for r in rows.values()) + " |")
    lines += ["", "Entities counted: " + ", ".join(f"{k}: direct {r['counts']['direct_entities'][1]}, quasi {r['counts']['quasi_entities'][1]}"
                                                   for k, r in list(rows.items())[:1]), "",
              "## Recall by identifier and entity type", "", "| Type | " + " | ".join(rows) + " |", "|---|" + "---|" * len(rows)]
    for t in sorted(next(iter(rows.values()))["by_type"]):
        lines.append(f"| {t} (n={next(iter(rows.values()))['by_type'][t]['n']}) | " +
                     " | ".join(pct(r["by_type"].get(t, {}).get("recall")) for r in rows.values()) + " |")
    md = "\n".join(lines) + "\n"
    (out / "report.md").write_text(md)
    (out / "report.json").write_text(json.dumps(rows, indent=1))
    (out / "chart.svg").write_text(svg_chart(rows))
    (out / "manifest.json").write_text(json.dumps({"run_id": out.name, "eval": "tab-official", "dataset": str(SRC),
                                                   "window_chars": 6000, "runs": {k: r["run"] for k, r in rows.items()},
                                                   "script": "scripts/tab_official.py"}, indent=1))
    print(md)
    print(f"recorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
