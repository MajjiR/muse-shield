"""Re-score saved entity-resolution predictions with the current scorer (no model calls).

    python scripts/er_rescore.py results/entity-resolution/<run>  [--gold-dir runs/er/v1] [--tab runs/er/tab/tab.docs.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield import resolution as R  # noqa: E402


def load_res(pred: dict | None, text: str) -> R.Resolution | None:
    if pred is None:
        return None
    ents = []
    for e in pred["entities"]:
        ms = [R.Mention(s, t, text[s:t], 0, R.is_reference(text[s:t]) and e["type"] in ("PERSON", "ORG")) for s, t in e["mentions"]]
        ents.append(R.Entity(e["id"], e["type"], e.get("role"), e.get("subtype"), e.get("owner"), ms))
    return R.Resolution(text, ents, [tuple(r) for r in pred["relations"]])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--gold-dir", type=Path, default=REPO / "runs/er/v1")
    ap.add_argument("--tab", type=Path, default=REPO / "runs/er/tab/tab.docs.jsonl")
    a = ap.parse_args(argv)
    report = json.loads((a.run / "report.json").read_text())
    for f in sorted(a.run.glob("*.preds.jsonl")):
        name = f.name.split(".")[0]
        src = a.tab if name == "tab" else a.gold_dir / f"{name}.docs.jsonl"
        gold = {d["uid"]: d for d in map(json.loads, src.read_text().splitlines())}
        rows = [json.loads(l) for l in f.read_text().splitlines()]
        scores = []
        for r in rows:
            g = gold[r["uid"]]
            r["score"] = R.score_doc(g, load_res(r["pred"], g["text"]), relaxed=name == "tab")
            scores.append(r["score"])
        agg = R.aggregate(scores)
        old = report["sets"].get(name, {})
        agg["seconds"], agg["tokens"] = old.get("seconds"), old.get("tokens")
        report["sets"][name] = agg
        f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{a.run.name} {name}: leak {agg['leak']:.3f} core {agg['core_leak']:.3f} person {agg['person_leak']:.3f} coref F1 {agg['coref']['f1']:.3f} "
              f"persons {agg['persons_resolved']}")
    report["rescored"] = "scripts/er_rescore.py (current scorer)"
    (a.run / "report.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
