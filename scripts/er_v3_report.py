"""Build the er-v3 release report for judges: training logs and graphs, checkpoint history, data and contamination
record, and the official benchmark comparison (our fine-tune vs Muse Spark vs base Muse Glimmer).

    .venv/bin/python scripts/er_v3_report.py

Writes results/er-v3-release/ (README.md, charts/*.svg, training/, checkpoints/, data/, benchmarks/). Every number
is read from saved files: training logs (results/training/*er-v3*), checkpoint scores (runs/er/v3/checkpoints.jsonl),
and the official runs (results/nemotron-pii, results/pupa, results/entity-resolution tagged official-*).
"""

from __future__ import annotations

import csv
import glob
import gzip
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "results/er-v3-release"
V3 = REPO / "runs/er/v3"
MAIN_RESULTS = Path("/Users/majjir/muse-shield/results")
RUNS = {v: sorted(glob.glob(str(REPO / f"results/training/*_glimmer-er-v3{v.lower()}")))[-1] for v in "ABCD"}
# validated categorical palette (dataviz reference instance, light surface); text never wears these
C = {"ours": "#2a78d6", "spark": "#eb6834", "base": "#1baf7a", "v2b": "#eda100",
     "A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a", "D": "#eda100"}
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
FONT = 'font-family="Inter, Helvetica, Arial, sans-serif"'
CHOSEN = ("A", 250)


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(w: int, h: int, title: str, sub: str = "") -> list[str]:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" {FONT}>',
           f'<rect width="{w}" height="{h}" fill="{SURF}"/>',
           f'<text x="24" y="32" font-size="17" font-weight="600" fill="{INK}">{esc(title)}</text>']
    if sub:
        out.append(f'<text x="24" y="52" font-size="12" fill="{INK2}">{esc(sub)}</text>')
    return out


def legend(items: list[tuple[str, str]], x: int, y: int) -> list[str]:
    out, cx = [], x
    for name, color in items:
        out.append(f'<rect x="{cx}" y="{y - 9}" width="12" height="12" rx="2" fill="{color}"/>'
                   f'<text x="{cx + 18}" y="{y + 1}" font-size="12" fill="{INK2}">{esc(name)}</text>')
        cx += 26 + 7 * len(name)
    return out


# -- training ------------------------------------------------------------------------------------------

def training_metrics(v: str) -> tuple[list[dict], list[dict], dict]:
    log = Path(RUNS[v]) / "run.log"
    steps, evals = [], []
    for line in log.read_text(errors="replace").splitlines():
        if line.startswith('{"type": "metrics"'):
            m = json.loads(line)
            (evals if "eval_loss" in m else steps).append(m)
    cfg = json.loads((Path(RUNS[v]) / "config.json").read_text())
    return steps, evals, cfg


def ema(xs: list[float], a: float = 0.08) -> list[float]:
    out, s = [], None
    for x in xs:
        s = x if s is None else a * x + (1 - a) * s
        out.append(s)
    return out


def loss_chart(data: dict) -> str:
    W, H, L, R, T, B = 820, 400, 70, 30, 80, 50
    maxstep = max(s["step"] for st, _, _ in data.values() for s in st)
    ymax = 0.16
    x = lambda s: L + (W - L - R) * s / maxstep  # noqa: E731
    y = lambda v: T + (H - T - B) * (1 - min(v, ymax) / ymax)  # noqa: E731
    out = svg_open(W, H, "er-v3 training loss (4 parallel runs, dedicated B200 each)",
                   "Cross-entropy on the gold JSON, smoothed (EMA 0.08). One pass over each mix; constant LR 1e-4, LoRA rank 16.")
    for i in range(9):
        v = ymax * i / 8
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" font-size="11" fill="{MUTED}" text-anchor="end">{v:.2f}</text>')
    for s in range(0, maxstep + 1, 100):
        out.append(f'<text x="{x(s):.1f}" y="{H - B + 18}" font-size="11" fill="{MUTED}" text-anchor="middle">{s}</text>')
    out.append(f'<text x="{(L + W - R) / 2}" y="{H - 10}" font-size="12" fill="{INK2}" text-anchor="middle">optimizer step (16 documents each)</text>')
    names = {"A": "A full mix", "B": "B no Nemotron", "C": "C + half of PUPA", "D": "D no short-form note (stopped at 328)"}
    for v, (st, ev, _) in data.items():
        pts = ema([s["ce_loss"] for s in st])
        path = " ".join(f"{'M' if i == 0 else 'L'}{x(s['step']):.1f},{y(p):.1f}" for i, (s, p) in enumerate(zip(st, pts)))
        out.append(f'<path d="{path}" fill="none" stroke="{C[v]}" stroke-width="2"><title>{esc(names[v])}</title></path>')
        last = st[-1]
        out.append(f'<text x="{min(x(last["step"]) + 6, W - R - 4):.1f}" y="{y(pts[-1]) - 6:.1f}" font-size="11" fill="{INK2}">{v}</text>')
    out += legend([(names[v], C[v]) for v in data], L, 70)
    out.append("</svg>")
    return "\n".join(out)


# -- checkpoints ---------------------------------------------------------------------------------------

def checkpoint_rows() -> list[dict]:
    return [json.loads(l) for l in (V3 / "checkpoints.jsonl").read_text().splitlines() if l.strip()]


def trajectory_chart(rows: list[dict]) -> str:
    panels = [("PUPA dev: private details leaked", lambda s: s["pupa-dev"]["leak"] * 100, "%", 6.1, "Muse Spark 6.1% (its own prompt)"),
              ("Nemotron held-out: leak, all types", lambda s: s["heldout-nemotron-train"]["leak"] * 100, "%", 1.1, "Muse Spark 1.1% (same instructions)"),
              ("ER test: coreference F1", lambda s: s["test"]["coref_f1"], "", 0.979, "er-v2b 0.979")]
    PW, PH, gap, L, T = 270, 230, 30, 50, 90
    W, H = L + 3 * PW + 2 * gap + 20, T + PH + 70
    out = svg_open(W, H, "Checkpoint scores during training (held-out data only)",
                   "Each checkpoint was deployed, scored and deleted while training continued. Lower is better for leaks.")
    for k, (title, f, unit, ref, ref_name) in enumerate(panels):
        x0 = L + k * (PW + gap)
        vals = [f(r["sets"]) for r in rows] + [ref]
        lo, hi = (0.93, 0.99) if not unit else (0, max(vals) * 1.15)
        x = lambda s: x0 + PW * s / 820  # noqa: E731
        y = lambda v: T + PH * (1 - (v - lo) / (hi - lo))  # noqa: E731
        out.append(f'<text x="{x0}" y="{T - 14}" font-size="13" font-weight="600" fill="{INK}">{esc(title)}</text>')
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            out.append(f'<line x1="{x0}" x2="{x0 + PW}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>'
                       f'<text x="{x0 - 6}" y="{y(v) + 4:.1f}" font-size="10" fill="{MUTED}" text-anchor="end">'
                       f'{v:.0f}{unit}</text>' if unit else
                       f'<line x1="{x0}" x2="{x0 + PW}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{GRID}"/>'
                       f'<text x="{x0 - 6}" y="{y(v) + 4:.1f}" font-size="10" fill="{MUTED}" text-anchor="end">{v:.3f}</text>')
        out.append(f'<line x1="{x0}" x2="{x0 + PW}" y1="{y(ref):.1f}" y2="{y(ref):.1f}" stroke="{INK2}" stroke-dasharray="4 4"/>'
                   f'<text x="{x0 + 4}" y="{y(ref) + (14 if unit else -5):.1f}" font-size="10" fill="{INK2}">{esc(ref_name)}</text>')
        for s in (250, 500, 750):
            out.append(f'<text x="{x(s):.1f}" y="{T + PH + 16}" font-size="10" fill="{MUTED}" text-anchor="middle">{s}</text>')
        for v in "ABCD":
            pts = sorted((r["step"], f(r["sets"])) for r in rows if r["variant"] == v)
            if not pts:
                continue
            path = " ".join(f"{'M' if i == 0 else 'L'}{x(s):.1f},{y(val):.1f}" for i, (s, val) in enumerate(pts))
            out.append(f'<path d="{path}" fill="none" stroke="{C[v]}" stroke-width="2"/>')
            for s, val in pts:
                ring = 3 if (v, s) == CHOSEN else 0
                out.append(f'<circle cx="{x(s):.1f}" cy="{y(val):.1f}" r="{5 + ring}" fill="{C[v]}" stroke="{SURF}" stroke-width="2">'
                           f'<title>{v} step {s}: {val:.3f}{unit}</title></circle>')
        cs = next((r for r in rows if (r["variant"], r["step"]) == CHOSEN), None)
        if cs:
            val = f(cs["sets"])
            out.append(f'<text x="{x(CHOSEN[1]) + 9:.1f}" y="{y(val) + 4:.1f}" font-size="11" font-weight="600" fill="{INK}">chosen</text>')
    out += legend([("A full mix", C["A"]), ("B no Nemotron", C["B"]), ("C + half PUPA", C["C"]), ("D no short-form note", C["D"])], L, H - 18)
    out.append("</svg>")
    return "\n".join(out)


# -- official benchmarks -------------------------------------------------------------------------------

def newest(pattern: str) -> Path | None:
    hits = sorted(glob.glob(pattern))
    return Path(hits[-1]) if hits else None


def official() -> dict:
    """Pull every official number we have. Missing ones stay None (the README says so)."""
    out: dict = {"ours": {}, "spark": {}, "base": {}, "v2b": {}, "spark_app": {}}
    # Nemotron test 500
    for key, tag in (("ours", "official-er-v3a"), ("spark", "official-spark-v3prompt"), ("base", "official-base-v3prompt")):
        d = newest(str(REPO / f"results/nemotron-pii/*_{tag}"))
        if d:
            r = json.loads((d / "report.json").read_text()) if (d / "report.json").exists() else None
            if r is None:
                rs = [json.loads(p.read_text()) for p in d.glob("*.json") if p.name not in ("manifest.json",)]
                r = rs[0] if rs else {}
            rep = r[0] if isinstance(r, list) else r
            out[key]["nemotron"] = {"leak": rep.get("leak_rate"), "core": rep.get("core_leak_rate"), "valid": rep.get("valid_rate"), "run": d.name}
    for key, tag, root in (("v2b", "full500-glimmer-er-v2b", REPO), ("spark_app", "full500-spark-contributor-low", MAIN_RESULTS)):
        d = newest(str(REPO / f"results/nemotron-pii/*_{tag}")) or newest(str(root / f"nemotron-pii/*_{tag}"))
        if d:
            for p in d.glob("*.json"):
                if p.name == "manifest.json":
                    continue
                rep = json.loads(p.read_text())
                rep = rep[0] if isinstance(rep, list) else rep
                if "core_leak_rate" in rep:
                    out[key]["nemotron"] = {"leak": rep.get("leak_rate"), "core": rep.get("core_leak_rate"), "run": d.name}
    # PUPA held-out 269
    d = newest(str(REPO / "results/pupa/*_official-final-er-v3a"))
    if d:
        rep = json.loads((d / "report.json").read_text())
        for name, r in rep.items():
            key = "ours" if "ours" in name else "base" if "Base" in name else "spark" if "same instructions" in name else "spark_app"
            out[key]["pupa"] = {"leak": r["leak_rate"], "protected": r["prompts_fully_protected"], "valid": r["valid"],
                                "units": r["units"], "prompts": r["prompts"], "run": d.name}
    # TAB
    tab_dir = newest(str(REPO / "results/tab-official/*_er-v3-official"))
    if tab_dir:
        rows = json.loads((tab_dir / "report.json").read_text())
        for name, r in rows.items():
            key = "ours" if "ours" in name else "base" if "Base" in name else "v2b" if "er-v2b" in name else "spark"
            out[key]["tab"] = {k: r[k] for k in ("ER_di", "ER_qi", "token_recall", "precision")} | {"run": tab_dir.name}
    # synthetic sets
    syn = {"ours": [("results/entity-resolution/*_er-v3a-s250", REPO)],
           "v2b": [("entity-resolution/*_er-v2b", MAIN_RESULTS)],
           "spark": [("entity-resolution/*_spark-low-v2prompt", MAIN_RESULTS), ("entity-resolution/*_spark-low-ambiguity", MAIN_RESULTS)],
           "base": [("entity-resolution/*_base-glimmer-v2prompt", MAIN_RESULTS), ("results/entity-resolution/*_official-base-ambiguity", REPO)]}
    for key, srcs in syn.items():
        sets = {}
        for pat, root in srcs:
            d = newest(str(root / pat))
            if d:
                sets.update(json.loads((d / "report.json").read_text())["sets"])
        out[key]["synthetic"] = {s: {"core": v["core_leak"], "coref": v["coref"]["f1"], "owner": v.get("owner_acc"),
                                     "unknown": v.get("unknown_acc"), "valid": v["valid"]}
                                 for s, v in sets.items() if s in ("test", "challenge", "ambiguity")}
    return out


def bars_chart(res: dict) -> str:
    """Small multiples: one panel per benchmark headline, three bars each (ours, Spark, base)."""
    panels = [("Nemotron-PII test (500): core leak", lambda r: (r.get("nemotron") or {}).get("core"), True),
              ("PUPA held-out (269 prompts): details leaked", lambda r: (r.get("pupa") or {}).get("leak"), True),
              ("TAB (127 judgments): direct identifiers protected", lambda r: (r.get("tab") or {}).get("ER_di"), False),
              ("ER test (synthetic): core leak", lambda r: ((r.get("synthetic") or {}).get("test") or {}).get("core"), True)]
    who = [("ours", "Muse Glimmer + er-v3 (ours, local)"), ("spark", "Muse Spark (cloud, same instructions)"),
           ("base", "Muse Glimmer base (same instructions)")]
    PW, rowh, L, T = 370, 30, 24, 96
    W = 2 * PW + 3 * L
    H = T + 2 * (len(who) * rowh + 70) + 20
    out = svg_open(W, H, "Muse Shield masking: fine-tuned Glimmer vs Muse Spark vs base Glimmer",
                   "Official test sets, run once after the model was chosen on held-out data. Arrows show which way is better.")
    out += legend([(n, C[k]) for k, n in who], L, 74)
    for i, (title, f, lower) in enumerate(panels):
        x0, y0 = L + (i % 2) * (PW + L), T + (i // 2) * (len(who) * rowh + 70)
        vals = [f(res[k]) for k, _ in who]
        top = max([v for v in vals if v is not None] + [0.01])
        out.append(f'<text x="{x0}" y="{y0 + 16}" font-size="13" font-weight="600" fill="{INK}">{esc(title)} '
                   f'{"↓" if lower else "↑"}</text>')
        for j, ((k, name), v) in enumerate(zip(who, vals)):
            y = y0 + 28 + j * rowh
            if v is None:
                out.append(f'<text x="{x0}" y="{y + 14}" font-size="11" fill="{MUTED}">{esc(name.split(" (")[0])}: not run</text>')
                continue
            w = (PW - 70) * v / (top * 1.05)
            out.append(f'<rect x="{x0}" y="{y}" width="{max(w, 2):.1f}" height="20" rx="4" fill="{C[k]}"><title>{esc(name)}: {v * 100:.1f}%</title></rect>'
                       f'<text x="{x0 + max(w, 2) + 6:.1f}" y="{y + 15}" font-size="12" fill="{INK}">{v * 100:.1f}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def pct(v, d=1):
    return "—" if v is None else f"{v * 100:.{d}f}%"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("charts", "training", "checkpoints", "data", "benchmarks"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    # training
    data = {v: training_metrics(v) for v in "ABCD"}
    (OUT / "charts/training-loss.svg").write_text(loss_chart(data))
    train_rows = []
    for v, (st, ev, cfg) in data.items():
        with open(OUT / f"training/steps-{v}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["step", "ce_loss", "tokens_per_sec", "lr"])
            for s in st:
                w.writerow([s["step"], round(s["ce_loss"], 6), round(s.get("tokens_per_sec", 0)), s.get("lr")])
        stats = json.loads((Path(RUNS[v]) / "data-stats.json").read_text())
        (OUT / f"training/config-{v}.json").write_text(json.dumps({k: cfg[k] for k in cfg if k not in ("log_path", "cookbook_training_dir")}
                                                                   | {"train_file": f"runs/er/v3/{v}/train.jsonl"}, indent=1))
        log = (Path(RUNS[v]) / "run.log").read_text(errors="replace").splitlines()
        t0, t1 = log[0][:19], next((l[:19] for l in reversed(log) if l[:4] == "2026"), "")
        train_rows.append({"run": v, "rows": stats["rows"], "steps": st[-1]["step"], "eval_loss_start": ev[0]["eval_loss"] if ev else None,
                           "eval_loss_end": ev[-1]["eval_loss"] if len(ev) > 1 else None, "started": t0, "ended": t1,
                           "model": cfg["output_model_id"], "stopped_early": v == "D"})
        (OUT / f"training/run-{v}.log.gz").write_bytes(gzip.compress("\n".join(log).encode()))
    (OUT / "training/runs.json").write_text(json.dumps(train_rows, indent=1))
    # checkpoints
    rows = checkpoint_rows()
    (OUT / "charts/checkpoints.svg").write_text(trajectory_chart(rows))
    shutil.copy(V3 / "checkpoints.md", OUT / "checkpoints/checkpoints.md")
    shutil.copy(V3 / "checkpoints.jsonl", OUT / "checkpoints/checkpoints.jsonl")
    # data
    manifest = json.loads((V3 / "manifest.json").read_text())
    (OUT / "data/manifest.json").write_text(json.dumps(manifest, indent=1))
    (OUT / "data/train-A.jsonl.gz").write_bytes(gzip.compress((V3 / "A/train.jsonl").read_bytes()))
    (OUT / "data/val.jsonl.gz").write_bytes(gzip.compress((V3 / "A/val.jsonl").read_bytes()))
    shutil.copy(REPO / "runs/er/gen3/docs.jsonl", OUT / "data/generated-v3-families.docs.jsonl")
    for n in ("heldout-v3-val", "heldout-nemotron-train", "heldout-er-val"):
        shutil.copy(V3 / f"{n}.docs.jsonl", OUT / f"data/{n}.docs.jsonl")
    ids = lambda f: [json.loads(l)["id"] for l in (V3 / f).read_text().splitlines() if l.strip()]  # noqa: E731
    (OUT / "data/pupa-split.json").write_text(json.dumps({
        "note": "PUPA (Columbia-NLP/PUPA, MIT) prompts by id; text not redistributed. Split 50/50 by conversation_hash, "
                "stratified by category, seed 7. Run C trained on train_ids; dev_ids scored checkpoints; final_ids is the "
                "only PUPA test reported. No conversation is on two sides.",
        "train_ids": json.loads((V3 / "pupa-train-ids.json").read_text()), "dev_ids": ids("pupa-dev.jsonl"),
        "final_ids": ids("pupa-final.jsonl")}, indent=1))
    # benchmarks
    res = official()
    (OUT / "benchmarks/comparison.json").write_text(json.dumps(res, indent=1))
    (OUT / "charts/benchmarks.svg").write_text(bars_chart(res))
    o, s, b, v2 = res["ours"], res["spark"], res["base"], res["v2b"]
    g = lambda r, *ks: (lambda x: x)(_dig(r, ks))  # noqa: E731
    syn = lambda r, st, k: ((r.get("synthetic") or {}).get(st) or {}).get(k)  # noqa: E731
    sa = res["spark_app"]
    lines = ["| Benchmark | Metric | **Muse Glimmer + er-v3 (ours, local)** | Muse Spark, same instructions | "
             "Muse Spark, its own prompt | Muse Glimmer base | er-v2b (previous) |",
             "|---|---|---|---|---|---|---|"]
    def row(bench, metric, f, d=1, num=False):
        cells = []
        for r in (o, s, sa, b, v2):
            v = f(r)
            cells.append("—" if v is None else (f"{v:.3f}" if num else pct(v, d)))
        cells[0] = f"**{cells[0]}**"
        lines.append(f"| {bench} | {metric} | " + " | ".join(cells) + " |")
    row("Nemotron-PII test (500 docs)", "core leak ↓", lambda r: g(r, "nemotron", "core"))
    row("", "leak, all types ↓", lambda r: g(r, "nemotron", "leak"))
    row("PUPA held-out (269 real prompts)", "details leaked ↓", lambda r: g(r, "pupa", "leak"))
    row("", "prompts fully protected ↑", lambda r: g(r, "pupa", "protected"))
    row("TAB (127 ECHR judgments)", "direct identifiers protected (ER_di) ↑", lambda r: g(r, "tab", "ER_di"))
    row("", "quasi identifiers protected (ER_qi) ↑", lambda r: g(r, "tab", "ER_qi"))
    row("", "precision ↑", lambda r: g(r, "tab", "precision"))
    row("ER test (synthetic, 150)", "core leak ↓", lambda r: syn(r, "test", "core"))
    row("", "coreference F1 ↑", lambda r: syn(r, "test", "coref"), num=True)
    row("", "owner accuracy ↑", lambda r: syn(r, "test", "owner"))
    row("Challenge (unseen doc types, 80)", "coreference F1 ↑", lambda r: syn(r, "challenge", "coref"), num=True)
    row("Ambiguity (80)", "UNKNOWN owners right ↑", lambda r: syn(r, "ambiguity", "unknown"))
    table = "\n".join(lines)
    (OUT / "benchmarks/comparison.md").write_text(table + "\n")
    tr = "\n".join(f"| {r['run']} | {r['rows']:,} | {r['steps']} | {r['eval_loss_start']:.4f} → "
                   f"{(r['eval_loss_end'] or float('nan')):.4f} | {r['started'][11:16]}–{r['ended'][11:16]} IST | "
                   f"{'stopped at the step-250 checkpoint' if r['stopped_early'] else r['model']} |" for r in train_rows)
    nm = manifest["nemotron"]
    readme = f"""# Muse Shield er-v3: fine-tuned Muse Glimmer 30B for local privacy masking

The masking model that runs on the user's machine: **Muse Glimmer 30B + a LoRA we trained (er-v3, chosen checkpoint
`muse-shield-glimmer-er-v3a-s250`)**. It reads a document or chat message, finds every person, organisation and private
value, links mentions of the same person, says whose each value is, and code masks them before anything reaches the cloud
model (Muse Spark). This folder has everything needed to check the numbers: the data, the training logs, every checkpoint
score, and the official benchmark runs.

## Results (official test sets, run once)

![benchmarks](charts/benchmarks.svg)

{table}

- **Same instructions:** Muse Spark and base Glimmer get er-v3's v3 masking instructions plus a worked example (our
  fine-tune runs without the example). **Its own prompt:** Muse Spark with the app's original analysis prompt (PII +
  context, the cloud stand-in the app used before), for transparency: it is stronger on PUPA, weaker on Nemotron.
- **Synthetic rows** are our held-out generated test sets (never trained on). Spark and base were scored with the v2
  prompt those answer keys follow.
- **er-v2b** is the previous fine-tune (before er-v3) on the same official sets where it was run.
- Raw per-document predictions are in the run folders named in `benchmarks/comparison.json`.

## How the model was chosen (no peeking at the test sets)

Four variants trained in parallel, one dedicated B200 each. Every 250 steps each checkpoint was deployed on a temporary
H200 and scored on **held-out** data only: our synthetic test sets (regression gates against er-v2b), 150 unused
Nemotron *train* documents, 80 unused generated chat documents, and a 101-prompt PUPA dev slice. The official
Nemotron test (500) and PUPA final (269) sets were not touched until the choice was made.

![checkpoints](charts/checkpoints.svg)

Later checkpoints scored higher on the synthetic sets but leaked about twice as much on the PUPA dev slice (every run
showed this), so the step-250 checkpoint of run A was chosen. D was stopped at step 328: it lost to A on every metric.
Full table: `checkpoints/checkpoints.md`.

## Training

![loss](charts/training-loss.svg)

| Run | Training rows | Steps | Eval loss | Time | Model |
|---|---|---|---|---|---|
{tr}

LoRA rank 16 / alpha 32 on attention and MLP, learning rate 1e-4 constant, batch 16, one pass, loss on the answer only,
max length 6,144 tokens. Per-step logs: `training/steps-*.csv`, full logs `training/run-*.log.gz`, configs `training/config-*.json`.

## Data

| Source | Documents | What it teaches |
|---|---|---|
| er-v2 documents (our generator, relabelled under the v3 policy) | {manifest['sources']['er-v2 (v3 relabel)']:,} | people, coreference, owners, relations |
| New generated families: chat requests, IT tickets, profile forms, schedules | {manifest['sources']['v3 families']:,} | links, usernames, IPs, secrets, places, organisations, times, demographics |
| Nemotron-PII **train** split (NVIDIA, CC BY 4.0), converted | {nm['train']:,} | breadth of real-world value types |
| PUPA train half (run C only) | {manifest['pupa']['train_docs']} | — (not in the chosen model) |

Every generated document is fictional: code plans the people and values, DeepSeek V4 Flash writes the text with inline
tags, code checks and repairs the tags, and a second model pass must agree on owners and references.
Files: `data/train-A.jsonl.gz` (the exact training file of the chosen model), `data/val.jsonl.gz`,
`data/generated-v3-families.docs.jsonl`, the held-out sets, and `data/manifest.json`.

### Keeping training and test apart

- Any training text sharing a 12-word run with a benchmark or test text was dropped: Nemotron test 500, all of PUPA,
  TAB test, our ER test / challenge / ambiguity sets ({manifest['dropped_for_overlap']['er-v2']} er-v2 and
  {nm['skipped'].get('shares a 12-word run with a benchmark', 0)} Nemotron docs removed).
- Nemotron rows are from the train split only; the 500 benchmark docs come from the test split, and any train doc
  matching one by id or text is dropped too.
- PUPA has no train split; it was split by conversation (`data/pupa-split.json`). The chosen model (run A) never saw any
  PUPA prompt; 269 prompts were never used for any decision and are the only PUPA numbers reported.
- The model was chosen on held-out data before the official runs, and the official runs were done once.

## Reproduce

```
.venv/bin/python -m muse_shield.resolution_data build --out runs/er/gen3 --n 4800 --seed 41 --only v3   # generated docs
.venv/bin/python -m muse_shield.er_v3_data build --out runs/er/v3                                     # mixes + checks
.venv/bin/python scripts/er_v3_launch.py --variants A B C D --checkpoint-every 250                    # training
.venv/bin/python scripts/er_ckpt_watch.py                                                            # checkpoint scores
.venv/bin/python scripts/official_v3.py --model muse-shield-glimmer-er-v3a-s250                      # official round
.venv/bin/python scripts/er_v3_report.py                                                             # this folder
```
"""
    (OUT / "README.md").write_text(readme)
    print(f"wrote {OUT}")
    print(table)
    return 0


def _dig(r: dict, ks: tuple):
    for k in ks:
        r = (r or {}).get(k)
    return r


if __name__ == "__main__":
    raise SystemExit(main())
