// Helpers shared by the in-page frames (composer.html, reply.html). These run on the
// extension's own origin inside meta.ai, so the page can't read them or their contents.

const PORTS = [8765, 8766, 8767, 8768, 8769]; // python -m muse_shield.app uses 8765 unless PORT is set
const LABEL = /<[A-Z][A-Z_]*_\d+>/g;
let API = null;

// The first local port with the extension routes (other apps, or an older engine, may hold 8765).
async function findEngine() {
  for (const port of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/ext/health`, { signal: AbortSignal.timeout(800) });
      const h = await r.json();
      if (h && h.ok && h.extension) {
        API = `http://127.0.0.1:${port}`;
        return h;
      }
    } catch {}
  }
  return null;
}

async function api(path, body) {
  if (!API && !(await findEngine())) throw new Error("Muse Shield engine isn't running on 127.0.0.1:8765–8769");
  const r = await fetch(API + path, body === undefined ? {} : {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `engine returned ${r.status}`);
  return data;
}

// Which tab this frame lives in (tabs.getCurrent can be empty in a frame: ask the service worker).
async function myTabId() {
  const t = await chrome.tabs.getCurrent().catch(() => null);
  if (t && t.id !== undefined) return t.id;
  return (await chrome.runtime.sendMessage({ type: "whoami" })).tabId;
}

function el(tag, cls = "", text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

// Masked text with its placeholders picked out.
function maskedNode(text) {
  const p = el("div", "masked");
  let i = 0;
  for (const m of (text || "").matchAll(LABEL)) {
    p.append(text.slice(i, m.index), el("code", "ph", m[0]));
    i = m.index + m[0].length;
  }
  p.append((text || "").slice(i));
  return p;
}

// Restored text: real values highlighted, with the placeholder Meta AI wrote on hover.
function segmentsNode(segments) {
  const p = el("div", "text");
  for (const s of segments || []) {
    if (!s.label) { p.append(s.text); continue; }
    const m = el("mark", s.kind === "context" ? "ctx" : s.kind === "unknown" ? "unknown" : "", s.text);
    m.title = s.kind === "unknown" ? `${s.label} isn't in this chat's vault` : `Meta AI wrote ${s.label}`;
    p.append(m);
  }
  return p;
}

// Tell the page how tall this frame needs to be (a number only; nothing private). Measure the
// content, not the document: the document is at least as tall as the frame, so it would only grow.
function reportHeight(tabId, extra, target = document.body) {
  let last = 0;
  const send = () => {
    const cs = getComputedStyle(document.body);
    const h = Math.ceil(target.offsetHeight + (target === document.body ? 0 : parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)));
    if (h === last) return;
    last = h;
    chrome.tabs.sendMessage(tabId, { ...extra, height: h }).catch(() => {});
  };
  new ResizeObserver(send).observe(target);
  send();
}
