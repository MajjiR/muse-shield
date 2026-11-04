"""Categorise each model's errors on the sector test, from the per-case predictions a run saved.

    .venv/bin/python scripts/error_analysis.py base=sectors-glimmer-base v2full=sectors-glimmer-v2full-preds ...

Entity errors are put in categories that point at a training fix:

| category | meaning |
|---|---|
| split | a gold PERSON "First Last" was output as separate parts |
| boundary | right type, but the span is longer or shorter than the gold span |
| type | the same span with a different type |
| miss | the gold entity was not output at all |
| extra | output that matches no gold entity (job titles, generic dates and so on) |

Context errors: the gold passage was missed (by kind), the kind was wrong, or an extra passage
was output where gold has none. Amount-role errors are counted too. Writes error-analysis.md and
errors.json (all examples) under results/error-analysis/<run>/.
"""

from __future__ import annotations

import collections
import glob
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield.evals import _norm  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402
from muse_shield.sector_eval import load_cases  # noqa: E402


def load_run(tag: str) -> dict:
    d = Path(sorted(glob.glob(str(RESULTS / "sector-test" / f"*_{tag}")))[-1])
    f = [p for p in d.glob("*.json") if p.name != "manifest.json"][0]
    rep = json.loads(f.read_text())
    rep = rep[0] if isinstance(rep, list) else rep
    if not rep.get("per_case") or "pred" not in next((c for c in rep["per_case"] if c.get("valid")), {}):
        raise SystemExit(f"{tag}: no per-case predictions saved")
    return {c["id"]: c for c in rep["per_case"]}


def analyse(cases, run: dict) -> dict:
    cat = collections.Counter()
    by_type = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    extra_texts = collections.Counter()
    ctx = collections.Counter()
    ctx_missed_kind = collections.Counter()
    roles = collections.Counter()
    invalid = 0
    for c in cases:
        r = run.get(c.id)
        if not r or not r.get("valid"):
            invalid += 1
            continue
        gold = [(e.text, e.type, e.role) for e in c.entities]
        pred = [tuple(p) for p in r["pred"]]
        g_keys = {(_norm(t), ty) for t, ty, _ in gold}
        p_keys = {(_norm(t), ty) for t, ty, _ in pred}
        used_pred = set()
        for t, ty, role in gold:
            k = (_norm(t), ty)
            if k in p_keys:
                if ty == "AMOUNT":
                    prole = next((pr for pt, pty, pr in pred if (_norm(pt), pty) == k), None)
                    roles["ok" if prole == role else "wrong"] += 1
                    if prole != role:
                        ex["role"].append(f"{t}: gold {role}, got {prole}")
                used_pred.add(k)
                continue
            nt = _norm(t)
            same_text = [(pt, pty) for pt, pty, _ in pred if _norm(pt) == nt]
            parts = [pt for pt, pty, _ in pred if pty == "PERSON" and _norm(pt) != nt and _norm(pt) in nt.split()]
            overlap = [pt for pt, pty, _ in pred if pty == ty and _norm(pt) != nt and (_norm(pt) in nt or nt in _norm(pt))]
            if ty == "PERSON" and len(parts) >= 1 and " " in t:
                kind = "split"
                used_pred.update((_norm(p), "PERSON") for p in parts)
            elif same_text:
                kind = "type"
                used_pred.update((_norm(p), pty) for p, pty in same_text)
                ex["type"].append(f"{t}: gold {ty}, got {same_text[0][1]}")
            elif overlap:
                kind = "boundary"
                used_pred.update((_norm(p), ty) for p in overlap)
                ex["boundary"].append(f"{ty} gold '{t}' got '{overlap[0]}'")
            else:
                kind = "miss"
                ex["miss"].append(f"{ty} '{t}'")
            cat[kind] += 1
            by_type[ty][kind] += 1
            if kind == "split":
                ex["split"].append(f"'{t}' -> {parts}")
        for pt, pty, _ in pred:
            k = (_norm(pt), pty)
            if k in g_keys or k in used_pred:
                continue
            cat["extra"] += 1
            by_type[pty]["extra"] += 1
            extra_texts[(pty, pt)] += 1
        gctx = [(set(g.sentences), g.kind) for g in c.contexts]
        pctx = [(set(s), k) for s, k, _ in r["pred_ctx"]]
        used = set()
        for gs, gk in gctx:
            hit = next((i for i, (ps, pk) in enumerate(pctx) if i not in used and ps & gs), None)
            if hit is None:
                ctx["missed"] += 1
                ctx_missed_kind[gk] += 1
            else:
                used.add(hit)
                ctx["kind ok" if pctx[hit][1] == gk else "wrong kind"] += 1
                if pctx[hit][1] != gk:
                    ex["ctx_kind"].append(f"gold {gk} got {pctx[hit][1]}")
        ctx["extra"] += len(pctx) - len(used)
    return {"invalid": invalid, "entity": dict(cat), "by_type": {t: dict(v) for t, v in by_type.items()},
            "extra_top": [[t, x, n] for (t, x), n in extra_texts.most_common(25)], "contexts": dict(ctx),
            "ctx_missed_by_kind": dict(ctx_missed_kind), "roles": dict(roles), "examples": {k: v[:40] for k, v in ex.items()}}


def main(argv: list[str]) -> int:
    cases = load_cases(REPO / "data/synth-v2/test")
    gold_n = sum(len(c.entities) for c in cases)
    gold_ctx = sum(len(c.contexts) for c in cases)
    res = {name: analyse(cases, load_run(tag)) for name, tag in (s.split("=", 1) for s in argv)}
    names = list(res)
    md = [f"# Sector test error analysis\n\n{len(cases)} paragraphs, {gold_n} gold entities, {gold_ctx} gold context passages.\n",
          "## Entity errors (count)\n", "| category | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k in ["split", "boundary", "type", "miss", "extra"]:
        md.append(f"| {k} | " + " | ".join(str(res[n]["entity"].get(k, 0)) for n in names) + " |")
    md.append("| invalid paragraphs | " + " | ".join(str(res[n]["invalid"]) for n in names) + " |")
    md += ["", "## Entity errors by type (miss+split+boundary+type / extra)\n", "| type | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    types = sorted({t for n in names for t in res[n]["by_type"]})
    for t in types:
        cells = []
        for n in names:
            v = res[n]["by_type"].get(t, {})
            cells.append(f"{sum(v.get(k, 0) for k in ('miss', 'split', 'boundary', 'type'))} / {v.get('extra', 0)}")
        md.append(f"| {t} | " + " | ".join(cells) + " |")
    md += ["", "## Contexts\n", "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k in ["kind ok", "wrong kind", "missed", "extra"]:
        md.append(f"| {k} | " + " | ".join(str(res[n]["contexts"].get(k, 0)) for n in names) + " |")
    kinds = sorted({k for n in names for k in res[n]["ctx_missed_by_kind"]})
    for k in kinds:
        md.append(f"| missed {k} | " + " | ".join(str(res[n]["ctx_missed_by_kind"].get(k, 0)) for n in names) + " |")
    md.append("| amount role wrong / ok | " + " | ".join(f"{res[n]['roles'].get('wrong', 0)} / {res[n]['roles'].get('ok', 0)}" for n in names) + " |")
    for n in names:
        md += ["", f"## {n}: most frequent extra outputs\n", ", ".join(f"{t}:'{x}'×{c}" for t, x, c in res[n]["extra_top"][:20])]
        for k in ["split", "boundary", "miss", "type", "ctx_kind", "role"]:
            if res[n]["examples"].get(k):
                md.append(f"- **{k}**: " + "; ".join(res[n]["examples"][k][:8]))
    out = RESULTS / "error-analysis" / new_run_id("sectors-" + "-".join(names), time.time(), git_version())
    out.mkdir(parents=True, exist_ok=True)
    (out / "error-analysis.md").write_text("\n".join(md) + "\n")
    (out / "errors.json").write_text(json.dumps({"runs": dict(s.split("=", 1) for s in argv), **res}, indent=2, ensure_ascii=False))
    print("\n".join(md))
    print(f"\nrecorded {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
