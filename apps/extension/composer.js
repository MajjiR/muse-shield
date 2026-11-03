// The Muse Shield composer: sits where meta.ai's message box was. You type here (an extension
// frame meta.ai can't read), detected details are underlined as you type, and only masked text
// is handed to meta.ai. It also drives the conversation: replies, restores, consent.

const PREVIEW_DELAY_MS = 900;
const MAX_ASK_ROUNDS = 2;
const TYPE_LABEL = { SENSITIVE_ATTRIBUTE: "sensitive detail", DEAL: "deal", DECISION: "decision", PLAN: "plan",
  NEGOTIATION: "negotiation", PROJECT: "project", HR: "HR matter" };

const $ = (id) => document.getElementById(id);
const input = $("input");
const state = {
  tabId: null, conversationId: null, chatId: null, analysis: false, busy: false,
  spans: [], keep: new Set(), extra: new Map(), previewTimer: null, previewSeq: 0, checking: false,
  requestId: 0, askRounds: 0,
  sent: null, // what you just sent: {message_id, text, spans, masked} or a consent note, until its bubble is covered
};

// -- status --------------------------------------------------------------------------------

function setStatus(text, kind = "") {
  $("status").textContent = text;
  $("status").className = `status ${kind ? `status--${kind}` : ""}`;
}

function idleStatus() {
  if (state.busy) return;
  if (!state.analysis) return;
  const n = visibleRanges().filter((r) => r.masked).length;
  if (state.checking) setStatus("Checking…", "muted");
  else if (input.value.trim() && n) setStatus(`${n} detail${n === 1 ? "" : "s"} will be masked`, "ok");
  else if (input.value.trim()) setStatus("Nothing sensitive found", "muted");
  else setStatus(state.chatId ? "Shielded chat" : "Masked on your device before Meta AI sees it", "muted");
}

function setBusy(busy, text) {
  state.busy = busy;
  $("send").disabled = busy || !state.analysis;
  input.readOnly = busy;
  if (busy) setStatus(text, "muted");
  else idleStatus();
}

// -- underlines (Grammarly-style) -----------------------------------------------------------

// Every place a detected span's text appears now, so underlines survive edits until the next check.
function visibleRanges() {
  const text = input.value;
  const out = [];
  const find = (needle, make) => {
    if (!needle) return;
    for (let i = text.indexOf(needle); i >= 0; i = text.indexOf(needle, i + needle.length)) out.push(make(i, i + needle.length));
  };
  for (const s of state.spans) {
    find(s.text, (start, end) => {
      const kept = state.keep.has(s.text) && !s.policy;
      return { start, end, span: s, kind: s.kind, kept, masked: !kept };
    });
  }
  for (const [value, type] of state.extra) {
    find(value, (start, end) => ({ start, end, span: { text: value, type, kind: "entity", policy: false, user: true }, kind: "entity", kept: false, masked: true, user: true }));
  }
  return out;
}

function renderBackdrop() {
  const text = input.value;
  const ranges = visibleRanges();
  const cuts = new Set([0, text.length]);
  for (const r of ranges) { cuts.add(r.start); cuts.add(r.end); }
  const points = [...cuts].sort((a, b) => a - b);
  const bd = $("backdrop");
  bd.replaceChildren();
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    const over = ranges.filter((r) => r.start <= a && b <= r.end);
    const ent = over.find((r) => r.kind === "entity");
    const ctx = over.find((r) => r.kind === "context");
    if (!ent && !ctx) { bd.append(text.slice(a, b)); continue; }
    const m = el("mark", [ctx ? (ctx.kept ? "u-ctx u-kept" : "u-ctx") : "", ent ? `u-ent t-${ent.span.type}${ent.kept ? " u-kept" : ""}${ent.user ? " u-user" : ""}` : ""].join(" "), text.slice(a, b));
    bd.append(m);
  }
  bd.append("\n"); // keeps the mirror as tall as the textarea when the text ends with a newline
  bd.scrollTop = input.scrollTop;
}

function autosize() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
  $("backdrop").style.height = input.style.height;
}

function schedulePreview() {
  clearTimeout(state.previewTimer);
  if (!input.value.trim() || !state.analysis) {
    state.spans = [];
    state.checking = false;
    renderBackdrop();
    idleStatus();
    return;
  }
  state.previewTimer = setTimeout(runPreview, PREVIEW_DELAY_MS);
}

async function runPreview() {
  const text = input.value;
  const seq = ++state.previewSeq;
  state.checking = true;
  idleStatus();
  try {
    const r = await api("/ext/preview", { text });
    if (seq !== state.previewSeq) return; // a newer check is on its way
    if (r.ok) state.spans = r.spans;
    else setStatus("Couldn't check this text; it will be checked again on send", "warn");
  } catch (e) {
    if (seq === state.previewSeq) setStatus(e.message, "error");
  } finally {
    if (seq === state.previewSeq) {
      state.checking = false;
      renderBackdrop();
      idleStatus();
    }
  }
}

// -- the popover: click an underline to keep or mask it ------------------------------------

function hidePop() {
  $("pop").hidden = true;
}

function showPop(range) {
  const s = range.span;
  const pop = $("pop");
  pop.replaceChildren();
  const kind = s.kind === "context" ? `${TYPE_LABEL[s.type] || s.type.toLowerCase()} passage` : (TYPE_LABEL[s.type] || s.type.toLowerCase());
  const head = el("div", "pop__head");
  head.append(el("span", `dot t-${s.type}`), el("strong", "", kind), el("span", "muted", ` · “${s.text.length > 48 ? s.text.slice(0, 48) + "…" : s.text}”`));
  pop.append(head);
  const row = el("div", "pop__row");
  if (s.policy) {
    pop.append(el("div", "muted small", "Always masked: names, IDs, contacts, secrets and addresses never leave your device."));
  } else if (s.user) {
    pop.append(el("div", "muted small", "You chose to mask this."));
    const b = el("button", "chip", "Unmask");
    b.onclick = () => { state.extra.delete(s.text); afterChoice(); };
    row.append(b);
  } else if (range.kept) {
    pop.append(el("div", "muted small", s.kind === "context" ? "This passage goes as written (names inside stay masked)." : "This goes to Meta AI as written."));
    const b = el("button", "chip chip--accent", "Mask it");
    b.onclick = () => { state.keep.delete(s.text); afterChoice(); };
    row.append(b);
  } else {
    pop.append(el("div", "muted small", s.kind === "context"
      ? `Hidden as one block${s.summary ? ` (“${s.summary}”)` : ""}. Meta AI can ask you to reveal it.`
      : "Meta AI sees a placeholder instead; you see the real value in its reply."));
    const b = el("button", "chip", s.kind === "context" ? "Send passage, keep names masked" : "Don't mask");
    b.onclick = () => { state.keep.add(s.text); afterChoice(); };
    row.append(b);
  }
  if (row.childElementCount) pop.append(row);
  pop.hidden = false;
}

function afterChoice() {
  hidePop();
  renderBackdrop();
  idleStatus();
  input.focus();
}

function onCaret() {
  const { selectionStart: a, selectionEnd: b, value } = input;
  const selected = value.slice(a, b);
  $("maskSel").hidden = !(b > a && selected.trim().length >= 2);
  if (b > a) { hidePop(); return; }
  const hits = visibleRanges().filter((r) => r.start <= a && a < r.end);
  const hit = hits.find((r) => r.kind === "entity") || hits[0];
  if (hit) showPop(hit); else hidePop();
}

$("maskBtn").addEventListener("mousedown", (e) => e.preventDefault()); // keep the selection
$("maskBtn").addEventListener("click", () => {
  const value = input.value.slice(input.selectionStart, input.selectionEnd).trim();
  if (value) state.extra.set(value, $("maskType").value);
  $("maskSel").hidden = true;
  afterChoice();
});

// -- sending -------------------------------------------------------------------------------

async function sendToMeta(outbound) {
  state.requestId += 1;
  const r = await chrome.tabs.sendMessage(state.tabId, { type: "send", text: outbound, requestId: state.requestId });
  if (!r || !r.ok) throw new Error(r?.error || "meta.ai didn't take the message");
  coverSent(r.userMessageId); // cover your bubble right away, before Meta AI starts replying
  return r;
}

async function submit() {
  const text = input.value.trim();
  if (!text || state.busy || !state.analysis) return;
  hidePop();
  clearTimeout(state.previewTimer);
  setBusy(true, "Masking on your device…");
  try {
    const r = await api("/ext/mask", { text, chat_id: state.chatId, keep: [...state.keep], extra: [...state.extra].map(([t, type]) => ({ text: t, type })) });
    if (!r.analysis_ok) throw new Error(`Not sent: ${r.error}`);
    state.chatId = r.chat_id;
    if (!state.conversationId) chrome.storage.session.set({ [`pending:${state.tabId}`]: { chatId: r.chat_id, at: Date.now() } });
    state.askRounds = 0;
    state.sent = { state: "user", message_id: r.message_id, text, spans: r.spans, masked: r.outbound };
    setBusy(true, "Sending masked text…");
    await sendToMeta(r.outbound);
    input.value = "";
    state.spans = [];
    state.keep.clear();
    state.extra.clear();
    autosize();
    renderBackdrop();
    setBusy(true, "Meta AI is replying…");
  } catch (e) {
    setBusy(false);
    setStatus(e.message, "error");
  }
}

// -- replies from meta.ai ------------------------------------------------------------------

function showReply(messageId, data) {
  chrome.storage.session.set({ [`r:${messageId}`]: data });
  chrome.tabs.sendMessage(state.tabId, { type: "mount-reply", messageId }).catch(() => {});
}

// Cover your sent bubble with what you typed (once per meta.ai id; ids can settle late on a new chat).
function coverSent(userMessageId) {
  const s = state.sent;
  if (!s || !userMessageId || s.covered === userMessageId) return;
  s.covered = userMessageId;
  const { message_id, covered, ...data } = s;
  showReply(userMessageId, data);
  if (message_id) api("/ext/link", { chat_id: state.chatId, message_id, site_message_id: userMessageId }).catch(() => {});
}

async function onReply(msg) {
  coverSent(msg.userMessageId);
  if (msg.state === "streaming") {
    if (state.chatId) {
      api("/ext/restore", { chat_id: state.chatId, text: msg.text })
        .then((r) => showReply(msg.messageId, { state: "streaming", segments: r.segments, masked: msg.text })).catch(() => {});
    }
    return;
  }
  if (msg.state === "error") {
    setBusy(false);
    setStatus(msg.error, "error");
    return;
  }
  try {
    const r = await api("/ext/reply", { chat_id: state.chatId, text: msg.text, message_id: msg.messageId });
    if (r.ask) {
      state.askRounds += 1;
      if (state.askRounds > MAX_ASK_ROUNDS) showReply(msg.messageId, { state: "done", segments: [{ text: "Meta AI kept asking for more context, so Muse Shield stopped asking you." }], masked: msg.text });
      else showReply(msg.messageId, { state: "ask", ask: r.ask, masked: msg.text });
    } else {
      showReply(msg.messageId, { state: "done", segments: r.segments, masked: msg.text, note: r.error || "" });
    }
  } catch (e) {
    setStatus(e.message, "error");
  }
  if (msg.conversationId && msg.conversationId !== state.conversationId) await openConversation(msg.conversationId, true);
  setBusy(false);
}

async function onConsent(msg) {
  const key = `r:${msg.messageId}`;
  const data = (await chrome.storage.session.get(key))[key];
  if (!data || data.state !== "ask" || state.busy) return;
  const ask = data.ask;
  setBusy(true, msg.decision === "allow" ? "Sending what you allowed…" : "Telling Meta AI you declined…");
  try {
    const r = await api("/ext/consent", { chat_id: ask.chat_id, label: ask.label, level: msg.level, decision: msg.decision, reason: ask.reason });
    await chrome.storage.session.set({ [key]: { ...data, state: "answered", decision: msg.decision, level: msg.level } });
    state.sent = { state: "note", text: msg.decision === "allow" ? `You let Meta AI see ${ask.label} (${msg.level}).` : `You declined to reveal ${ask.label}.`,
      masked: r.outbound };
    await sendToMeta(r.outbound);
    setBusy(true, "Meta AI is replying…");
  } catch (e) {
    setBusy(false);
    setStatus(e.message, "error");
  }
}

// -- which meta.ai conversation we're in ----------------------------------------------------

async function openConversation(conversationId, keepChat = false) {
  state.conversationId = conversationId;
  const pendingKey = `pending:${state.tabId}`;
  if (conversationId && !keepChat) {
    // A new chat's first message went out from a composer that has since reloaded: bind that vault chat.
    const p = (await chrome.storage.session.get(pendingKey))[pendingKey];
    if (p && Date.now() - p.at < 5 * 60 * 1000) { state.chatId = p.chatId; keepChat = true; }
  }
  if (conversationId) chrome.storage.session.remove(pendingKey);
  try {
    const b = await api("/ext/bind", { conversation_id: conversationId, chat_id: keepChat ? state.chatId : null });
    state.analysis = b.analysis;
    if (!keepChat || b.chat_id) state.chatId = b.chat_id;
    if (!b.analysis) setStatus(`Masking is off: ${b.analysis_off_reason}`, "error");
    if (!keepChat) {
      adoptPage();
      for (const m of b.messages) {
        if (m.role === "assistant" && m.site_message_id) showReply(m.site_message_id, { state: "done", segments: m.segments, masked: m.masked });
        if (m.role === "user" && m.site_message_id) showReply(m.site_message_id, { state: "user", text: m.text, spans: m.spans, masked: m.masked });
      }
    }
  } catch (e) {
    state.analysis = false;
    setStatus(e.message, "error");
  }
  $("send").disabled = state.busy || !state.analysis;
  if (!keepChat) setBusy(false);
}

// Restore what's already on the page (chats from before this tab, or whose binding was lost).
// meta.ai renders history after load, so look again shortly after.
async function adoptPage() {
  for (const wait of [300, 1500, 4000]) {
    await new Promise((r) => setTimeout(r, wait));
    try {
      const page = await chrome.tabs.sendMessage(state.tabId, { type: "page-messages" });
      if (!page || page.conversationId !== state.conversationId || !page.messages.length) continue;
      const r = await api("/ext/adopt", { conversation_id: state.conversationId, messages: page.messages });
      if (r.chat_id && !state.chatId) state.chatId = r.chat_id;
      for (const [id, data] of Object.entries(r.items)) showReply(id, data);
    } catch {}
  }
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "consent" && msg.tabId === state.tabId) { onConsent(msg); return; }
  if (!sender.tab || sender.tab.id !== state.tabId) return;
  if (msg.type === "url") {
    if (msg.conversationId && state.chatId && !state.conversationId) openConversation(msg.conversationId, true);
    else if (!state.busy) openConversation(msg.conversationId);
  }
  if (msg.type === "reply" && msg.requestId === state.requestId) onReply(msg);
});

// -- wiring --------------------------------------------------------------------------------

input.addEventListener("input", () => { autosize(); renderBackdrop(); idleStatus(); schedulePreview(); });
input.addEventListener("scroll", () => { $("backdrop").scrollTop = input.scrollTop; });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
  if (e.key === "Escape") hidePop();
});
input.addEventListener("click", onCaret);
input.addEventListener("keyup", (e) => { if (e.key.startsWith("Arrow") || e.key === "Home" || e.key === "End") onCaret(); });
input.addEventListener("select", onCaret);
$("send").addEventListener("click", submit);
$("shield").addEventListener("click", () => chrome.storage.local.set({ shieldOn: false }));
const restoreBtn = $("restore");
const showRestore = (on) => {
  restoreBtn.textContent = on ? "👁 Real values" : "👁 Meta's view";
  restoreBtn.title = on ? "Showing your real values in this chat. Click to see exactly what Meta AI sees." : "Showing exactly what Meta AI sees. Click to restore your real values.";
  restoreBtn.classList.toggle("chip--on", on);
};
chrome.storage.local.get({ restoreOn: true }).then((v) => showRestore(v.restoreOn));
chrome.storage.onChanged.addListener((c, area) => { if (area === "local" && c.restoreOn) showRestore(c.restoreOn.newValue); });
restoreBtn.addEventListener("click", async () => {
  const { restoreOn = true } = await chrome.storage.local.get("restoreOn");
  chrome.storage.local.set({ restoreOn: !restoreOn });
});

(async () => {
  state.tabId = await myTabId();
  reportHeight(state.tabId, { type: "composer-height" }, document.querySelector(".box"));
  const engine = await findEngine();
  if (!engine) {
    setStatus("Start the engine: python -m muse_shield.app", "error");
    $("send").disabled = true;
    return;
  }
  const page = await chrome.tabs.sendMessage(state.tabId, { type: "status" }).catch(() => ({}));
  await openConversation(page.conversationId || null);
  autosize();
  renderBackdrop();
  input.focus();
})();
