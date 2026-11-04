"""Plot a training run's loss curve from steps.csv into a self-contained HTML page.

    python3 scripts/plot_training.py results/training/<run>/

Writes <run>/loss.html: per-step loss (thin, muted) with a 10-step moving average,
hover readout, table view, light and dark themes.
"""

from __future__ import annotations

import csv
import html
import json
import sys
from pathlib import Path


def moving_average(values: list[float], window: int = 10) -> list[float]:
    out, acc = [], []
    for v in values:
        acc.append(v)
        if len(acc) > window:
            acc.pop(0)
        out.append(sum(acc) / len(acc))
    return out


def render(run: Path) -> str:
    rows = list(csv.DictReader((run / "steps.csv").open()))
    steps = [int(r["step"]) for r in rows]
    loss = [float(r["loss"]) for r in rows]
    avg = moving_average(loss)
    evals = [json.loads(l) for l in (run / "evals.jsonl").read_text().splitlines()] if (run / "evals.jsonl").exists() else []
    w, h, pad_l, pad_r, pad_t, pad_b = 720, 300, 56, 90, 16, 36
    xmax, ymax = max(steps), max(loss) * 1.08
    x = lambda s: pad_l + (s - 1) / max(xmax - 1, 1) * (w - pad_l - pad_r)  # noqa: E731
    y = lambda v: pad_t + (1 - v / ymax) * (h - pad_t - pad_b)  # noqa: E731
    grid = "".join(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                   f'<text x="{pad_l - 8}" y="{y(t) + 4:.1f}" class="axis" text-anchor="end">{t:.3f}</text>'
                   for t in [ymax * i / 4 for i in range(5)])
    xt = "".join(f'<text x="{x(s):.1f}" y="{h - 12}" class="axis" text-anchor="middle">{s}</text>'
                 for s in sorted({1, *range(50, xmax + 1, 50), xmax}))
    raw = " ".join(f"{x(s):.1f},{y(v):.1f}" for s, v in zip(steps, loss))
    sm = " ".join(f"{x(s):.1f},{y(v):.1f}" for s, v in zip(steps, avg))
    data = json.dumps([{"s": s, "l": l, "a": round(a, 5)} for s, l, a in zip(steps, loss, avg)])
    table = "".join(f"<tr><td>{s}</td><td>{l:.4f}</td><td>{a:.4f}</td></tr>" for s, l, a in zip(steps, loss, avg))
    ev = "".join(f"<li><b>{html.escape(e['label'])}</b>: exact match {e.get('exact_match', 0):.1%}, fields "
                 f"{html.escape(json.dumps(e.get('field_accuracy', {})))}</li>" for e in evals)
    first, last = sum(loss[:5]) / min(5, len(loss)), sum(loss[-5:]) / min(5, len(loss))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Training loss</title><style>
.viz-root{{color-scheme:light;--surface-1:#fcfcfb;--text-primary:#0b0b0b;--text-secondary:#52514e;--grid:#e4e3df;--s0:#2a78d6;--raw:#b9b8b3}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])) .viz-root{{color-scheme:dark;--surface-1:#1a1a19;--text-primary:#f0efec;--text-secondary:#c3c2b7;--grid:#3a3a37;--s0:#3987e5;--raw:#5a5955}}}}
:root[data-theme="dark"] .viz-root{{color-scheme:dark;--surface-1:#1a1a19;--text-primary:#f0efec;--text-secondary:#c3c2b7;--grid:#3a3a37;--s0:#3987e5;--raw:#5a5955}}
body{{margin:0}} .viz-root{{background:var(--surface-1);color:var(--text-primary);font:14px/1.45 -apple-system,system-ui,sans-serif;padding:24px 16px;min-height:100vh}}
main{{max-width:760px;margin:0 auto}} h1{{font-size:18px;margin:0 0 4px}} .meta{{color:var(--text-secondary);font-size:12px}}
svg{{width:100%;height:auto;display:block;margin-top:12px}} .grid{{stroke:var(--grid)}} .axis{{fill:var(--text-secondary);font-size:11px}}
.raw{{fill:none;stroke:var(--raw);stroke-width:1}} .avg{{fill:none;stroke:var(--s0);stroke-width:2}} .lbl{{fill:var(--text-primary);font-size:12px}}
.legend{{display:flex;gap:16px;color:var(--text-secondary);font-size:12px;margin-top:10px}} .sw{{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:6px}}
#tip{{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);padding:4px 8px;border-radius:6px;font-size:12px;opacity:0}}
details{{margin-top:12px;color:var(--text-secondary)}} table{{border-collapse:collapse;font-size:12px}} td,th{{padding:2px 10px;border-bottom:1px solid var(--grid);color:var(--text-primary)}}
</style></head><body><div class="viz-root"><main>
<h1>Training loss · {html.escape(run.name)}</h1>
<div class="meta">{len(steps)} steps · first-5 average {first:.4f} → last-5 average {last:.4f} ({(last - first) / first:+.0%})</div>
<div class="legend"><span><i class="sw" style="background:var(--raw)"></i>loss per step</span><span><i class="sw" style="background:var(--s0)"></i>10-step moving average</span></div>
<svg id="c" viewBox="0 0 {w} {h}" role="img" aria-label="Training loss by step">{grid}{xt}
<polyline class="raw" points="{raw}"/><polyline class="avg" points="{sm}"/>
<text x="{x(steps[-1]) + 6:.1f}" y="{y(avg[-1]) + 4:.1f}" class="lbl">{avg[-1]:.4f}</text>
<line id="cross" y1="{pad_t}" y2="{h - pad_b}" stroke="var(--text-secondary)" stroke-width="1" opacity="0"/>
<text x="{w / 2}" y="{h}" class="axis" text-anchor="middle">step</text></svg>
<ul>{ev}</ul>
<details><summary>Table view</summary><table><tr><th>step</th><th>loss</th><th>moving avg</th></tr>{table}</table></details>
</main><div id="tip" role="tooltip"></div></div>
<script>
const D={data}, svg=document.getElementById('c'), tip=document.getElementById('tip'), cross=document.getElementById('cross');
const X0={pad_l}, X1={w - pad_r}, XMAX={xmax};
svg.addEventListener('mousemove',e=>{{const r=svg.getBoundingClientRect(), vx=(e.clientX-r.left)/r.width*{w};
 const s=Math.round(1+(vx-X0)/(X1-X0)*(XMAX-1)); const d=D.find(p=>p.s===Math.min(Math.max(s,1),XMAX))||D[D.length-1];
 const px=X0+(d.s-1)/Math.max(XMAX-1,1)*(X1-X0); cross.setAttribute('x1',px); cross.setAttribute('x2',px); cross.setAttribute('opacity',.5);
 tip.textContent=`step ${{d.s}} · loss ${{d.l.toFixed(4)}} · avg ${{d.a.toFixed(4)}}`; tip.style.opacity=1;
 tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px'; tip.style.top=(e.clientY+14)+'px';}});
svg.addEventListener('mouseleave',()=>{{tip.style.opacity=0;cross.setAttribute('opacity',0)}});
</script></body></html>
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    run = Path(argv[1])
    (run / "loss.html").write_text(render(run))
    print(f"wrote {run / 'loss.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
