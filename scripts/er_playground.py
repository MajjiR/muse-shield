"""A local page for trying the entity-resolution engine on any document.

    /Users/majjir/muse-shield/.venv/bin/python scripts/er_playground.py --port 8790

Paste a document (or pick one of the 10 workflow examples), run it through the fine-tuned Glimmer
deployment from runs/er/serve.json (scripts/er_serve.py up ...), and see the masked text, every
mention coloured by identity, owners and relations. "Muse Spark" runs the same document through cloud
Spark for comparison: it sends the text to Meta, so use test documents only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield import resolution as R  # noqa: E402
from muse_shield.analysis import ContractError  # noqa: E402
from muse_shield.backends import GlimmerBackend, MetaModelBackend  # noqa: E402
from muse_shield.config import load_env  # noqa: E402

EXAMPLES = REPO / "data/er-playground/examples.json"
SERVE = REPO / "runs/er/serve.json"


def backend(name: str):
    if name == "spark":
        return MetaModelBackend(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), "muse-spark-1.3",
                                os.environ.get("MODEL_API_KEY", ""), name="muse_spark", synthetic_only=True,
                                reasoning_effort="low", max_tokens=12000), True, "Muse Spark 1.3 (cloud, low effort)"
    if not SERVE.exists():
        raise RuntimeError("no Glimmer deployment is running (scripts/er_serve.py up <model>)")
    s = json.loads(SERVE.read_text())
    return (GlimmerBackend("https://api.fireworks.ai/inference/v1", s["route"], os.environ["FIREWORKS_API_KEY"],
                           max_tokens=4000, timeout=300.0), False, f"Glimmer 30B + {s['model']} LoRA")


def resolve(text: str, model: str) -> dict:
    b, example, label = backend(model)
    msgs = R.messages(text, example=example)
    t0, usage, raw, err, res = time.perf_counter(), {"prompt_tokens": 0, "completion_tokens": 0}, "", "", None
    for _ in (1, 2):
        raw, u = b._call(msgs)
        for k in usage:
            usage[k] += u.get(k, 0)
        try:
            res = R.parse(raw, text)
            break
        except ContractError as exc:
            err = str(exc)
            msgs = msgs + [{"role": "assistant", "content": raw},
                           {"role": "user", "content": f"That output broke the contract ({err}). Reply with only the corrected JSON object."}]
    out = {"model": label, "latency_s": round(time.perf_counter() - t0, 1), "usage": usage, "raw": raw}
    if res is None:
        return out | {"error": err}
    masked = R.mask(res)
    labels = {e["placeholder"]: e for e in masked["entities"]}
    by_id = {}
    reg = R.Registry()
    for e in res.entities:  # same labels as mask(): mint in the same order with a fresh registry
        if any(not m.reference for m in e.mentions):
            by_id[e.id] = reg.label_for(e)
    spans = [{"start": m.start, "end": m.end, "entity": e.id, "placeholder": by_id.get(e.id, e.id), "type": e.type,
              "reference": m.reference} for e in res.entities for m in e.mentions]
    return out | {"masked": masked["masked"], "entities": list(labels.values()), "relations": masked["relations"],
                  "spans": sorted(spans, key=lambda s: s["start"]), "dropped": res.dropped}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entity Resolution Playground</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--mute:#6b6b70;--line:#e3e3e0;--acc:#5b5bd6}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1c1c1f;--ink:#ececf0;--mute:#9b9ba3;--line:#2c2c31;--acc:#8b8bff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,system-ui,sans-serif}
header{padding:18px 24px;border-bottom:1px solid var(--line)}h1{font-size:18px;margin:0}header p{margin:4px 0 0;color:var(--mute)}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;padding:16px 24px}
@media (max-width:900px){main{grid-template-columns:1fr;padding:16px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);margin:0 0 8px}
textarea{width:100%;min-height:340px;border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--bg);color:var(--ink);font:13px/1.5 ui-monospace,Menlo,monospace}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
select,button{font:inherit;padding:7px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc);cursor:pointer}button:disabled{opacity:.5}
pre,.doc{white-space:pre-wrap;word-wrap:break-word;font:13px/1.6 ui-monospace,Menlo,monospace;margin:0}
.m{border-radius:4px;padding:0 2px}.ref{background:none!important;border-bottom:2px dotted}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:500}.pill{font:12px ui-monospace,Menlo,monospace;padding:1px 6px;border-radius:10px}
.mute{color:var(--mute)}ul.check{margin:4px 0 0;padding-left:18px}.warn{color:#b26a00}.full{grid-column:1/-1}
details summary{cursor:pointer;color:var(--mute)}
</style></head><body>
<header><h1>Entity resolution playground</h1>
<p id="status" class="mute">Loading…</p></header>
<main>
<section class="card"><h2>Document</h2>
<div class="row"><select id="ex"><option value="">Pick a workflow example…</option></select>
<select id="model"><option value="glimmer">Glimmer (fine-tuned)</option><option value="spark">Muse Spark (cloud, for comparison)</option></select>
<button class="primary" id="go">Resolve</button><span id="time" class="mute"></span></div>
<textarea id="text" placeholder="Paste a document…"></textarea>
<div id="checkbox" class="mute" style="margin-top:8px"></div>
<p class="warn" style="font-size:12px">Use test documents only: both models run in the cloud (Fireworks for Glimmer, Meta for Spark).</p>
</section>
<section class="card"><h2>Mentions by identity</h2><div id="doc" class="doc mute">Run a document to see each mention coloured by who it refers to. Dotted = pronoun or description (kept readable).</div></section>
<section class="card"><h2>Masked text (what Meta would see)</h2><pre id="masked" class="mute">—</pre></section>
<section class="card"><h2>Identities, owners and relations</h2><div id="table" class="mute">—</div><div id="rels"></div></section>
<section class="card full"><details><summary>Raw model output</summary><pre id="raw"></pre></details></section>
</main>
<script>
const $=id=>document.getElementById(id);let EX=[];
const hue=s=>{let h=0;for(const c of s)h=(h*31+c.charCodeAt(0))%360;return h};
const col=(s,a)=>`hsla(${hue(s)},70%,55%,${a})`;
const esc=t=>t.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
fetch('/api/status').then(r=>r.json()).then(s=>{$('status').textContent=s.glimmer?`Glimmer model: ${s.glimmer.model} on ${s.glimmer.deployment}`:'No Glimmer deployment running: only Spark is available.'});
fetch('/api/examples').then(r=>r.json()).then(xs=>{EX=xs;xs.forEach((x,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${x.sector}: ${x.title}`;$('ex').appendChild(o)})});
$('ex').onchange=()=>{const x=EX[$('ex').value];if(!x)return;$('text').value=x.text;
 $('checkbox').innerHTML='<b>What a correct answer looks like</b><ul class="check">'+x.check.map(c=>`<li>${esc(c)}</li>`).join('')+'</ul>'};
$('go').onclick=async()=>{const text=$('text').value;if(!text.trim())return;$('go').disabled=true;$('time').textContent='Resolving…';
 try{const r=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,model:$('model').value})});
 const d=await r.json();$('raw').textContent=d.raw||d.error||'';
 if(d.error){$('time').textContent='Error: '+d.error;return}
 $('time').textContent=`${d.model} · ${d.latency_s}s · ${d.usage.completion_tokens} output tokens${d.dropped?` · ${d.dropped} mentions not found`:''}`;
 let html='',cur=0;for(const s of d.spans){if(s.start<cur)continue;html+=esc(text.slice(cur,s.start));
  html+=`<span class="m${s.reference?' ref':''}" style="background:${col(s.entity,.22)};border-color:${col(s.entity,.9)}" title="${s.placeholder} · ${s.type}">${esc(text.slice(s.start,s.end))}</span>`;cur=s.end}
 $('doc').className='doc';$('doc').innerHTML=html+esc(text.slice(cur));
 $('masked').className='';$('masked').innerHTML=esc(d.masked).replace(/&lt;([A-Z_]+_\d+)&gt;/g,(m,p)=>`<span class="pill" style="background:${col(p,.2)}">&lt;${p}&gt;</span>`);
 const rows=d.entities.map(e=>`<tr><td><span class="pill" style="background:${col(e.placeholder,.2)}">${e.placeholder}</span></td><td>${e.type}${e.subtype?' · '+e.subtype:''}${e.role?' · '+esc(e.role):''}</td><td>${e.owner?`<span class="pill">${e.owner}</span>`:'<span class="mute">—</span>'}</td><td>${esc(e.values.join(' | '))}${e.references.length?`<div class="mute">refs: ${esc(e.references.join(', '))}</div>`:''}</td></tr>`).join('');
 $('table').className='';$('table').innerHTML=`<table><tr><th>Placeholder</th><th>Type · role</th><th>Owner</th><th>Values and references</th></tr>${rows}</table>`;
 $('rels').innerHTML=d.relations.length?'<h2 style="margin-top:12px">Relations</h2>'+d.relations.map(r=>`<div><span class="pill">${r[0]}</span> ${r[1]} <span class="pill">${r[2]}</span></div>`).join(''):'';
 }catch(e){$('time').textContent='Error: '+e}finally{$('go').disabled=false}};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/examples":
            return self._send(200, EXAMPLES.read_bytes())
        if self.path == "/api/status":
            s = json.loads(SERVE.read_text()) if SERVE.exists() else None
            return self._send(200, json.dumps({"glimmer": s}).encode())
        self._send(404, b'{"error": "not found"}')

    def do_POST(self):  # noqa: N802
        if self.path != "/api/resolve":
            return self._send(404, b'{"error": "not found"}')
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            out = resolve(str(body.get("text", "")), body.get("model", "glimmer"))
        except Exception as exc:  # noqa: BLE001 - show the reason on the page
            out = {"error": f"{type(exc).__name__}: {exc}"}
        self._send(200, json.dumps(out, ensure_ascii=False).encode())

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} {fmt % args}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    load_env()
    print(f"entity-resolution playground on http://localhost:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
