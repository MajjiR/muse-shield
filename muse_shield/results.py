"""Versioned, timestamped record of every eval run: data, settings and charts.

Each run lands in results/<eval>/<run_id>/ with
    manifest.json        when, code version + git commit, dataset, sample hash, settings per model
    <backend>.json       the full metrics report
    <backend>.preds.jsonl raw predictions, for re-scoring and error analysis later
    compare.md           side-by-side table
    report.html          charts (light/dark, hover, table view)
and one line is appended to results/index.jsonl. results/README.md is regenerated
from the index so final stats across all runs are in one place.

run_id = <YYYYMMDD-HHMMSS>_v<package version>+<git sha>[-dirty]_<tag>
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .config import REPO_ROOT

RESULTS = REPO_ROOT / "results"

HEADLINE = [  # (key, label, lower_is_better)
    ("leak_rate", "Leak rate", True),
    ("core_leak_rate", "Core leak rate", True),
    ("span_recall", "Span recall", False),
    ("span_precision", "Span precision", False),
    ("type_accuracy", "Type accuracy", False),
    ("valid_rate", "Valid JSON", False),
]


def git_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "muse_shield"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else None


def new_run_id(tag: str, when: float | None = None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(when))
    safe = "".join(c if c.isalnum() or c in "-." else "-" for c in tag) or "run"
    return f"{stamp}_v{__version__}+{git_version()}_{safe}"


def save_run(eval_name: str, tag: str, reports: list[dict], preds: dict[str, list[dict]], *,
             settings: dict, dataset: dict, compare_md: str, root: Path = RESULTS,
             when: float | None = None, imported_from: str | None = None) -> Path:
    run_id = new_run_id(tag, when)
    if imported_from:  # the code version at run time is unknown; don't claim today's commit
        run_id = run_id.replace(f"+{git_version()}", "+imported")
    out = root / eval_name / run_id
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id, "eval": eval_name, "tag": tag,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(when)),
        "version": __version__, "git": "unknown (imported)" if imported_from else git_version(),
        "command": f"imported from {imported_from}" if imported_from else " ".join(sys.argv),
        "dataset": dataset, "settings": settings,
        "backends": [r["backend"] for r in reports],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for r in reports:
        (out / f"{r['backend']}.json").write_text(json.dumps(r, indent=2))
    for name, rows in preds.items():
        (out / f"{name}.preds.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in rows))
    (out / "compare.md").write_text(compare_md + "\n")
    (out / "report.html").write_text(render_html(manifest, reports))

    with (root / "index.jsonl").open("a") as f:
        for r in reports:
            f.write(json.dumps({
                "run_id": run_id, "eval": eval_name, "tag": tag, "created": manifest["created"],
                "version": __version__, "git": manifest["git"], "backend": r["backend"], "model": r.get("model"),
                "docs": r.get("docs") or r.get("n"), "settings": settings.get(r["backend"], {}),
                **{k: r.get(k) for k, _, _ in HEADLINE}, "cost_usd": r.get("cost_usd"),
                "cost_basis": (r.get("cost") or {}).get("basis"), "seconds": r.get("seconds"),
                "path": str(out.relative_to(root)),
            }) + "\n")
    write_readme(root)
    return out


def write_readme(root: Path = RESULTS) -> None:
    index = root / "index.jsonl"
    rows = [json.loads(l) for l in index.read_text().splitlines() if l.strip()] if index.exists() else []
    pct = lambda x: "–" if x is None else f"{x:.1%}"  # noqa: E731
    lines = ["# Muse Shield eval results", "",
             "Every eval run, newest first. Each row links to its folder: manifest (code version, git commit, settings, "
             "dataset hash), full reports, raw predictions, comparison table and charts (`report.html`).", "",
             "Benchmark data: [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII), CC BY 4.0.", "",
             "| run | eval | tag | model | docs | leak ↓ | core leak ↓ | recall ↑ | precision ↑ | valid JSON | cost |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    total = sum(r["cost_usd"] for r in rows if r.get("cost_usd") is not None)
    lines[4:4] = [f"Total recorded eval spend: **${total:.2f}** (token cost for API models; run time x GPU rate for "
                  "on-demand deployments, excluding idle time between runs).", ""]
    for r in sorted(rows, key=lambda r: r["run_id"], reverse=True):
        cost = "–" if r.get("cost_usd") is None else f"${r['cost_usd']:.2f}"
        if r.get("cost_basis") == "gpu_time":
            cost += " GPU"
        lines.append(f"| [{r['run_id']}]({r['path']}/report.html) | {r['eval']} | {r['tag']} | {r['backend']} `{r.get('model')}` | "
                     f"{r.get('docs')} | {pct(r.get('leak_rate'))} | {pct(r.get('core_leak_rate'))} | {pct(r.get('span_recall'))} | "
                     f"{pct(r.get('span_precision'))} | {pct(r.get('valid_rate'))} | {cost} |")
    (root / "README.md").write_text("\n".join(lines) + "\n")


# -- charts ---------------------------------------------------------------------
# Categorical slots 1-3 of the reference palette (validated all-pairs, light and dark).
# Up to three models per chart; more fold into "Other" rather than generating hues.
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70"]


def _bars_svg(chart_id: str, groups: list[tuple[str, list[float | None]]], series: list[str], lower_better: dict[str, bool]) -> str:
    """Horizontal grouped bars, 0-100%. One row group per metric, one bar per model."""
    bar_h, gap, group_gap, label_w, plot_w = 12, 2, 18, 150, 460
    width = label_w + plot_w + 70
    height = sum(len(series) * (bar_h + gap) - gap + group_gap for _ in groups) + 24
    parts = [f'<svg id="{chart_id}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{chart_id}-t" class="chart">',
             f'<title id="{chart_id}-t">{html.escape(chart_id)}</title>']
    for x in (0, 0.25, 0.5, 0.75, 1.0):  # recessive grid
        gx = label_w + x * plot_w
        parts.append(f'<line x1="{gx}" x2="{gx}" y1="4" y2="{height - 18}" class="grid"/>'
                     f'<text x="{gx}" y="{height - 4}" class="axis" text-anchor="middle">{int(x * 100)}%</text>')
    y = 6
    for label, values in groups:
        block = len(series) * (bar_h + gap) - gap
        arrow = " ↓" if lower_better.get(label) else " ↑"
        parts.append(f'<text x="{label_w - 10}" y="{y + block / 2 + 4}" class="glabel" text-anchor="end">{html.escape(label)}{arrow}</text>')
        for i, (name, v) in enumerate(zip(series, values)):
            if v is not None:
                w = max(v * plot_w, 1.5)
                tip = html.escape(f"{name} · {label}: {v:.1%}")
                parts.append(f'<path d="M{label_w},{y} h{max(w - 4, 0)} a4,4 0 0 1 4,4 v{bar_h - 8} a4,4 0 0 1 -4,4 h{-max(w - 4, 0)} z" '
                             f'class="s{i}" data-tip="{tip}"/>'
                             f'<rect x="{label_w}" y="{y - 1}" width="{plot_w}" height="{bar_h + 2}" class="hit" data-tip="{tip}"/>'
                             f'<text x="{label_w + w + 6}" y="{y + bar_h - 2}" class="val">{v:.1%}</text>')
            else:
                parts.append(f'<text x="{label_w + 6}" y="{y + bar_h - 2}" class="val">n/a</text>')
            y += bar_h + gap
        y += group_gap - gap
    parts.append("</svg>")
    return "".join(parts)


def _table(groups: list[tuple[str, list[float | None]]], series: list[str]) -> str:
    head = "".join(f"<th>{html.escape(s)}</th>" for s in series)
    body = "".join("<tr><th>" + html.escape(g) + "</th>" + "".join(f"<td>{'–' if v is None else f'{v:.1%}'}</td>" for v in vals) + "</tr>"
                   for g, vals in groups)
    return f'<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>'


def render_html(manifest: dict, reports: list[dict]) -> str:
    reports = reports[:3]
    names = [f"{r['backend']}" for r in reports]
    headline = [(label, [r.get(k) for r in reports]) for k, label, _ in HEADLINE if any(r.get(k) is not None for r in reports)]
    lower = {label: lb for _, label, lb in HEADLINE}
    types = sorted({t for r in reports for t in (r.get("recall_by_type") or {})})
    by_type = [(t, [(r.get("recall_by_type") or {}).get(t) for r in reports]) for t in types]
    legend = "".join(f'<span class="key"><i class="sw s{i}"></i>{html.escape(n)} <code>{html.escape(str(r.get("model")))}</code></span>'
                     for i, (n, r) in enumerate(zip(names, reports)))
    css_series = lambda pal: "".join(f"--s{i}:{c};" for i, c in enumerate(pal))  # noqa: E731
    sections = [("Headline metrics", "headline", headline, lower)]
    if by_type:
        sections.append(("Recall by PII type", "by-type", by_type, {}))
    body = ""
    for title, cid, groups, lb in sections:
        body += (f'<section><h2>{title}</h2>{_bars_svg(cid, groups, names, lb)}'
                 f'<details><summary>Table view</summary>{_table(groups, names)}</details></section>')
    meta = html.escape(f"{manifest['run_id']} · {manifest['created']} · git {manifest['git']} · {manifest['dataset'].get('name', '')} "
                       f"n={manifest['dataset'].get('docs') or (reports[0].get('docs') if reports else '')}")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Muse Shield eval</title><style>
.viz-root{{color-scheme:light;--surface-1:#fcfcfb;--text-primary:#0b0b0b;--text-secondary:#52514e;--grid:#e4e3df;{css_series(SERIES_LIGHT)}}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])) .viz-root{{color-scheme:dark;--surface-1:#1a1a19;--text-primary:#f0efec;--text-secondary:#c3c2b7;--grid:#3a3a37;{css_series(SERIES_DARK)}}}}}
:root[data-theme="dark"] .viz-root{{color-scheme:dark;--surface-1:#1a1a19;--text-primary:#f0efec;--text-secondary:#c3c2b7;--grid:#3a3a37;{css_series(SERIES_DARK)}}}
body{{margin:0}} .viz-root{{background:var(--surface-1);color:var(--text-primary);font:14px/1.45 -apple-system,system-ui,sans-serif;padding:24px 16px;min-height:100vh}}
main{{max-width:760px;margin:0 auto}} h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:15px;margin:28px 0 8px}}
.meta{{color:var(--text-secondary);font-size:12px;word-break:break-all}} .legend{{display:flex;flex-wrap:wrap;gap:14px;margin:14px 0 0}}
.key{{display:inline-flex;align-items:center;gap:6px;color:var(--text-secondary)}} .sw{{width:12px;height:12px;border-radius:3px;display:inline-block}}
.chart{{width:100%;height:auto;display:block}} .grid{{stroke:var(--grid);stroke-width:1}} .axis,.val{{fill:var(--text-secondary);font-size:11px}}
.glabel{{fill:var(--text-primary);font-size:12px}} .hit{{fill:transparent}} {''.join(f'.s{i}{{fill:var(--s{i});background:var(--s{i})}}' for i in range(3))}
path.s0,path.s1,path.s2{{stroke:var(--surface-1);stroke-width:2;paint-order:stroke}}
details{{margin-top:8px;color:var(--text-secondary)}} table{{border-collapse:collapse;margin-top:8px;font-size:13px}}
th,td{{padding:4px 10px;border-bottom:1px solid var(--grid);text-align:left;color:var(--text-primary)}}
#tip{{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);padding:4px 8px;border-radius:6px;font-size:12px;opacity:0;transition:opacity .1s}}
code{{font-size:11px}}
</style></head><body><div class="viz-root"><main>
<h1>Muse Shield · {html.escape(manifest['eval'])} · {html.escape(manifest['tag'])}</h1>
<div class="meta">{meta}</div><div class="legend">{legend}</div>{body}
</main><div id="tip" role="tooltip"></div></div>
<script>
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{{const t=e.target.closest('[data-tip]');
if(!t){{tip.style.opacity=0;return}} tip.textContent=t.dataset.tip;tip.style.opacity=1;
tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(e.clientY+14)+'px';}});
</script></body></html>
"""


def import_benchmark_dir(run_dir: Path, tag: str, settings: dict | None = None, dataset: dict | None = None) -> Path:
    """Record an existing runs/benchmarks/<stamp>/ folder into the registry."""
    from .config import load_env
    from .costs import deployment_info, run_cost

    load_env()
    reports = [json.loads(p.read_text()) for p in sorted(run_dir.glob("*.json"))]
    gpu_cache: dict[str, dict | None] = {}
    for r in reports:  # older reports used per-token prices for everything: re-cost with today's rules
        model = str(r.get("model"))
        if "#" in model and model not in gpu_cache:
            gpu_cache[model] = deployment_info(model, os.environ.get("FIREWORKS_API_KEY", ""))
        r["cost"] = run_cost(model, r.get("tokens") or {}, float(r.get("seconds") or 0), gpu_cache.get(model))
        r["cost"]["detail"]["recosted_on_import"] = True
        r["cost_usd"] = r["cost"]["usd"]
    preds = {p.name.removesuffix(".preds.jsonl"): [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
             for p in sorted(run_dir.glob("*.preds.jsonl"))}
    compare = (run_dir / "compare.md").read_text() if (run_dir / "compare.md").exists() else ""
    try:
        when = time.mktime(time.strptime(run_dir.name, "%Y%m%d-%H%M%S"))
    except ValueError:
        when = run_dir.stat().st_mtime
    return save_run("nemotron-pii", tag, reports, preds, settings=settings or {}, dataset=dataset or {"name": "nvidia/Nemotron-PII"},
                    compare_md=compare, when=when, imported_from=str(run_dir))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m muse_shield.results")
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="record an existing runs/benchmarks/<stamp> folder")
    imp.add_argument("run_dir", type=Path)
    imp.add_argument("--tag", required=True)
    sub.add_parser("readme", help="regenerate results/README.md from the index")
    args = ap.parse_args(argv)
    if args.cmd == "import":
        print(import_benchmark_dir(args.run_dir, args.tag))
    else:
        write_readme()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
