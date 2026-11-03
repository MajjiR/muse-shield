// Muse Shield side panel: your words and Meta AI's restored replies live only here.
// It talks to the local engine (127.0.0.1) and drives the meta.ai tab through content.js.

const PORTS = [8765, 8766, 8767, 8768, 8769]; // python -m muse_shield.app uses 8765 unless PORT is set
let API = "http://127.0.0.1:8765";
const META = /^https:\/\/(www\.)?meta\.ai\//;
const LABEL = /<[A-Z][A-Z_]*_\d+>/g;
const MAX_ASK_ROUNDS = 2;

const $ = (id) => document.getElementById(id);
const state = { tabId: null, conversationId: null, chatId: null, busy: false, live: null, askRounds: 0, requestId: 0, analysis: false };

// -- engine -------------------------------------------------------------------------------

// Find the engine: the first local port whose /health answers like Muse Shield (others may hold 8765).
async function findEngine() {
  for (const port of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(800) });
      const h = await r.json();
      if (h && h.ok && "analysis" in h) {
        API = `http://127.0.0.1:${port}`;
        return true;
      }
    } catch {}
  }
  return false;
}

async function api(path, body) {
  const r = await fetch(API + path, body === undefined ? {} : {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `engine returned ${r.status}`);
  return data;
}

// -- the meta.ai tab ------------------------------------------------------------------------

function toTab(msg) {
  return chrome.tabs.sendMessage(state.tabId, msg);
}

async function sync() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !META.test(tab.url || "")) {
    state.tabId = null;
    setStatus("Open <a href='https://www.meta.ai/' target='_blank'>meta.ai</a> in this tab to use Muse Shield.", "warn");
    render([]);
    setBusy(false);
    return;
  }
  state.tabId = tab.id;
  if (!(await findEngine())) {
    setStatus("Can't find the Muse Shield engine on 127.0.0.1:8765–8769. Start it with <code>python -m muse_shield.app</code>.", "error");
    return;
  }
  let page;
  try {
    page = await toTab({ type: "status" });
  } catch {
    setStatus("Reload the meta.ai tab once so Muse Shield can attach to it.", "warn");
    return;
  }
  await openConversation(page.conversationId);
}

async function openConversation(conversationId, keepChat = false) {
  state.conversationId = conversationId;
  try {
    const b = await api("/ext/bind", { conversation_id: conversationId, chat_id: keepChat ? state.chatId : null });
    state.analysis = b.analysis;
    if (!keepChat || b.chat_id) state.chatId = b.chat_id;
    if (!keepChat) render(b.messages);
    if (!b.analysis) setStatus(`Masking is off: ${escapeHtml(b.analysis_off_reason)}`, "error");
    else if (!conversationId) setStatus("New chat. Your first message carries a short privacy note for Meta AI.", "ok");
    else if (!b.chat_id) setStatus("This chat started without Muse Shield. New messages are shielded, starting with a privacy note.", "warn");
    else setStatus("Shielded chat. Meta AI sees placeholders; real values stay on this device.", "ok");
  } catch (e) {
    setStatus(`Can't reach the Muse Shield engine at ${API}. Start it with <code>python -m muse_shield.app</code>.`, "error");
  }
  if (!keepChat) setBusy(false); // keepChat happens mid-send: the reply is still coming
}

chrome.tabs.onActivated.addListener(sync);
chrome.tabs.onUpdated.addListener((tabId, info) => { if (tabId === state.tabId && info.status === "complete") sync(); });

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!sender.tab || sender.tab.id !== state.tabId) return;
  if (msg.type === "url") {
    // A new chat got its id from its first message: bind it to the vault chat we just used.
    if (msg.conversationId && state.chatId && !state.conversationId) openConversation(msg.conversationId, true);
    else if (!state.busy) openConversation(msg.conversationId);
  }
  if (msg.type === "reply" && msg.requestId === state.requestId) onReply(msg);
});

// -- sending ------------------------------------------------------------------------------

async function sendOutbound(outbound) {
  state.requestId += 1;
  showLive();
  const r = await toTab({ type: "send", text: outbound, requestId: state.requestId });
  if (!r || !r.ok) throw new Error(r?.error || "meta.ai didn't take the message");
}

async function onSubmit(e) {
  e?.preventDefault();
  const text = $("input").value.trim();
  if (!text || state.busy || !state.tabId) return;
  setBusy(true, "Masking on your device…");
  try {
    const r = await api("/ext/mask", { text, chat_id: state.chatId });
    if (!r.analysis_ok) throw new Error(`Not sent: ${r.error}`);
    state.chatId = r.chat_id;
    state.askRounds = 0;
    $("input").value = "";
    const bubble = addUser(text, r.spans, r.outbound);
    if ($("review").checked && !(await confirmSend(bubble, r.outbound))) {
      setBusy(false);
      return;
    }
    setBusy(true, "Sending masked text to Meta AI…");
    await sendOutbound(r.outbound);
    setBusy(true, "Meta AI is replying…");
  } catch (err) {
    if (!$("input").value) $("input").value = text;
    addNote(err.message, "error");
    setBusy(false);
  }
}

function confirmSend(bubble, outbound) {
  return new Promise((resolve) => {
    bubble.querySelector("details").open = true;
    const row = el("div", "confirm");
    const go = el("button", "", "Send to Meta AI");
    const no = el("button", "secondary", "Cancel");
    go.onclick = () => { row.remove(); resolve(true); };
    no.onclick = () => { row.remove(); addNote("Not sent.", "muted"); resolve(false); };
    row.append(go, no);
    bubble.append(row);
    setBusy(true, "Check what Meta AI will see, then send.");
  });
}

async function onReply(msg) {
  if (msg.state === "streaming") {
    if (state.chatId) {
      api("/ext/restore", { chat_id: state.chatId, text: msg.text })
        .then((r) => fillLive(r.segments, msg.text)).catch(() => {});
    }
    return;
  }
  if (msg.state === "error") {
    dropLive();
    addNote(msg.error, "error");
    setBusy(false);
    return;
  }
  try {
    const r = await api("/ext/reply", { chat_id: state.chatId, text: msg.text, message_id: msg.messageId });
    dropLive();
    if (r.ask) {
      state.askRounds += 1;
      if (state.askRounds > MAX_ASK_ROUNDS) addNote("Meta AI keeps asking for more context; stopped.", "error");
      else addAsk(r.ask);
    } else {
      if (r.error) addNote(r.error, "warn");
      addAssistant(r.segments, msg.text);
    }
  } catch (err) {
    dropLive();
    addNote(err.message, "error");
  }
  if (msg.conversationId && msg.conversationId !== state.conversationId) await openConversation(msg.conversationId, true);
  setBusy(false);
}

async function answerAsk(card, ask, decision, level) {
  card.querySelectorAll("button, input").forEach((b) => (b.disabled = true));
  setBusy(true, decision === "allow" ? "Sending what you allowed…" : "Telling Meta AI you declined…");
  try {
    const r = await api("/ext/consent", { chat_id: ask.chat_id, label: ask.label, level, decision, reason: ask.reason });
    card.classList.add(decision === "allow" ? "ask--allowed" : "ask--denied");
    card.querySelector(".ask__actions").replaceChildren(el("span", "muted small",
      decision === "allow" ? `You allowed ${ask.label} (${level}).` : `You declined ${ask.label}.`));
    await sendOutbound(r.outbound);
    setBusy(true, "Meta AI is replying…");
  } catch (err) {
    addNote(err.message, "error");
    setBusy(false);
  }
}

// -- rendering ------------------------------------------------------------------------------

function el(tag, cls = "", text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function setStatus(html, kind) {
  $("status").innerHTML = html;
  $("status").className = `status status--${kind}`;
}

function setBusy(busy, label) {
  state.busy = busy;
  $("sendBtn").disabled = busy || !state.tabId || !state.analysis;
  $("sendBtn").textContent = busy ? (label || "Working…") : "Mask & send";
}

function scroll() {
  $("log").scrollTop = $("log").scrollHeight;
}

// The masked text with its placeholders picked out.
function maskedNode(text) {
  const pre = el("div", "masked");
  let i = 0;
  for (const m of text.matchAll(LABEL)) {
    pre.append(text.slice(i, m.index), el("code", "ph", m[0]));
    i = m.index + m[0].length;
  }
  pre.append(text.slice(i));
  return pre;
}

function sentDetails(outbound, summary = "What Meta AI sees") {
  const d = el("details");
  d.append(el("summary", "", summary), maskedNode(outbound));
  return d;
}

// Your message, with what was masked highlighted (spans are offsets into your text).
function userText(text, spans) {
  const p = el("div", "text");
  const marks = (spans || []).filter((s) => s.kind === "context" || !s.in_context).sort((a, b) => a.start - b.start);
  let i = 0;
  for (const s of marks) {
    if (s.start < i) continue;
    p.append(text.slice(i, s.start));
    const m = el("mark", s.kind === "context" ? "ctx" : "", text.slice(s.start, s.end));
    m.title = `Sent as ${s.placeholder}`;
    p.append(m);
    i = s.end;
  }
  p.append(text.slice(i));
  return p;
}

function segmentsNode(segments) {
  const p = el("div", "text");
  for (const s of segments || []) {
    if (!s.label) { p.append(s.text); continue; }
    const m = el("mark", s.kind === "context" ? "ctx" : s.kind === "unknown" ? "unknown" : "", s.text);
    m.title = s.kind === "unknown" ? "Not in this chat's vault" : `Meta AI wrote ${s.label}`;
    p.append(m);
  }
  return p;
}

function addUser(text, spans, outbound) {
  const b = el("div", "msg msg--user");
  b.append(userText(text, spans), sentDetails(outbound));
  $("log").append(b);
  scroll();
  return b;
}

function addAssistant(segments, masked) {
  const b = el("div", "msg msg--assistant");
  b.append(el("div", "who", "Meta AI"), segmentsNode(segments), sentDetails(masked, "What Meta AI wrote"));
  $("log").append(b);
  scroll();
}

function addNote(text, kind = "muted") {
  $("log").append(el("div", `note note--${kind}`, text));
  scroll();
}

function showLive() {
  dropLive();
  state.live = el("div", "msg msg--assistant msg--live");
  state.live.append(el("div", "who", "Meta AI"), el("div", "text dots", "…"));
  $("log").append(state.live);
  scroll();
}

function fillLive(segments) {
  if (!state.live) return;
  state.live.querySelector(".text").replaceWith(segmentsNode(segments));
  scroll();
}

function dropLive() {
  state.live?.remove();
  state.live = null;
}

function addAsk(ask) {
  const card = $("tpl-ask").content.firstElementChild.cloneNode(true);
  card.querySelector(".ask__label").textContent = ask.label;
  card.querySelector(".ask__reason").textContent = ask.reason ? `“${ask.reason}”` : "";
  const preview = card.querySelector(".ask__preview");
  const levels = Object.keys(ask.previews);
  let level = ask.level;
  const show = () => { preview.textContent = ask.previews[level]; };
  if (levels.length > 1) {
    const hints = { shape: "structure, details still masked", summary: "one-line gist", full: "the real text" };
    for (const lv of levels) {
      const lab = el("label", "level");
      const r = el("input");
      r.type = "radio";
      r.name = `lv-${ask.label}-${Date.now()}`;
      r.checked = lv === level;
      r.onchange = () => { level = lv; show(); };
      lab.append(r, ` ${lv} `, el("span", "muted small", `(${hints[lv]})`));
      card.querySelector(".ask__levels").append(lab);
    }
  }
  show();
  card.querySelector(".ask__allow").onclick = () => answerAsk(card, ask, "allow", level);
  card.querySelector(".ask__deny").onclick = () => answerAsk(card, ask, "deny", level);
  $("log").append(card);
  scroll();
}

function render(messages) {
  $("log").replaceChildren();
  for (const m of messages) {
    if (m.role === "user") addUser(m.text, m.spans, m.masked);
    else if (m.role === "assistant") addAssistant(m.segments, m.masked);
    else if (m.role === "reveal") addNote(m.decision === "allow" ? `You allowed ${m.label} (${m.level}).` : `You declined ${m.label}.`);
  }
}

// -- wiring -------------------------------------------------------------------------------

$("composer").addEventListener("submit", onSubmit);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) onSubmit(e);
});
chrome.storage.local.get({ shieldOn: true, review: false }).then((v) => {
  $("shield").checked = v.shieldOn;
  $("review").checked = v.review;
});
$("shield").addEventListener("change", (e) => chrome.storage.local.set({ shieldOn: e.target.checked }));
$("review").addEventListener("change", (e) => chrome.storage.local.set({ review: e.target.checked }));
window.addEventListener("focus", () => $("input").focus());

setBusy(false);
sync();
