// Muse Shield content script for meta.ai.
//
// It never sees a real value: the side panel masks your message on 127.0.0.1 and hands this
// script only the masked text. Here we lock meta.ai's own composer (so nothing raw is typed
// into the page), put the masked text in it, press Send, and read Meta AI's reply back out.

const SEL = {
  composer: '[contenteditable="true"][data-testid="composer-input"]',
  send: '[data-testid="composer-send-button"]',
  item: "[data-message-item][data-message-role]",
  assistant: '[data-testid="assistant-message"]',
  thinking: '[data-testid="thinking-status"]',
};
const REPLY_TIMEOUT_MS = 180000;

let shieldOn = true;
let inserting = false; // our own synthetic edits pass the lock

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const squash = (s) => (s || "").replace(/\s+/g, "");
const post = (msg) => chrome.runtime.sendMessage(msg).catch(() => {}); // the panel may be closed

function conversationId() {
  const m = location.pathname.match(/^\/prompt\/([^/?#]+)/);
  return m ? m[1] : null;
}

async function waitFor(fn, ms, every = 100) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const v = fn();
    if (v) return v;
    await sleep(every);
  }
  return null;
}

// -- the lock over meta.ai's composer ---------------------------------------------------------

const lock = document.createElement("div");
lock.className = "muse-shield-lock";
lock.innerHTML = '<span class="muse-shield-lock__icon">🛡️</span><span>Muse Shield is on. Type in the side panel, so Meta AI only sees masked text.</span><button type="button">Open panel</button>';
lock.querySelector("button").addEventListener("click", () => post({ type: "open-panel" }));

function composerBox() {
  const ed = document.querySelector(SEL.composer);
  const send = document.querySelector(SEL.send);
  if (!ed) return null;
  let box = ed;
  while (box.parentElement && send && !box.contains(send)) box = box.parentElement;
  return box;
}

function placeLock() {
  const box = shieldOn && composerBox();
  if (!box) {
    lock.remove();
    return;
  }
  const r = box.getBoundingClientRect();
  Object.assign(lock.style, { top: `${r.top}px`, left: `${r.left}px`, width: `${r.width}px`, height: `${r.height}px` });
  if (!lock.isConnected) document.documentElement.appendChild(lock);
}
setInterval(placeLock, 250);
window.addEventListener("resize", placeLock);

// Keystrokes, paste, drop and dictation into the real composer are blocked while the shield is on
// (it autofocuses, so the overlay alone isn't enough). Our own edits are synthetic and pass.
for (const type of ["beforeinput", "keydown", "keypress", "paste", "drop", "compositionstart"]) {
  window.addEventListener(type, (e) => {
    if (!shieldOn || inserting || !e.isTrusted) return;
    const ed = document.querySelector(SEL.composer);
    if (ed && e.target instanceof Node && ed.contains(e.target)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      lock.classList.remove("muse-shield-lock--nudge");
      void lock.offsetWidth;
      lock.classList.add("muse-shield-lock--nudge");
    }
  }, true);
}

chrome.storage.local.get({ shieldOn: true }).then((v) => { shieldOn = v.shieldOn; placeLock(); });
chrome.storage.onChanged.addListener((c) => { if (c.shieldOn) { shieldOn = c.shieldOn.newValue; placeLock(); } });

// -- writing into meta.ai -------------------------------------------------------------------

async function placeText(text) {
  const ed = await waitFor(() => document.querySelector(SEL.composer), 5000);
  if (!ed) throw new Error("meta.ai's message box isn't on this page");
  inserting = true;
  try {
    ed.focus();
    window.getSelection().selectAllChildren(ed);
    await sleep(60); // Lexical picks up the selection on selectionchange
    ed.dispatchEvent(new InputEvent("beforeinput", { inputType: "deleteContentBackward", bubbles: true, cancelable: true }));
    await sleep(60);
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    ed.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }));
    const ok = await waitFor(() => squash(ed.innerText) === squash(text), 1500);
    if (!ok) throw new Error("couldn't put the masked text into meta.ai's message box");
  } finally {
    inserting = false;
  }
}

async function pressSend() {
  const btn = await waitFor(() => {
    const b = document.querySelector(SEL.send);
    return b && !b.disabled && b.getAttribute("aria-disabled") !== "true" ? b : null;
  }, 3000);
  if (!btn) throw new Error("meta.ai's Send button isn't available");
  inserting = true;
  try {
    btn.click();
  } finally {
    inserting = false;
  }
}

// -- reading Meta AI's reply ----------------------------------------------------------------

function assistantIds() {
  return new Set([...document.querySelectorAll(SEL.item)].filter((e) => e.dataset.messageRole === "assistant").map((e) => e.dataset.messageId));
}

// Rendered markdown -> plain text that keeps paragraphs, list markers and code blocks.
function toText(root) {
  let out = "";
  const nl = () => { if (out && !out.endsWith("\n")) out += "\n"; };
  const walk = (n) => {
    if (n.nodeType === Node.TEXT_NODE) { out += n.nodeValue; return; }
    if (n.nodeType !== Node.ELEMENT_NODE) return;
    const tag = n.tagName;
    if (["BUTTON", "STYLE", "SCRIPT", "svg", "SVG"].includes(tag) || n.getAttribute("aria-hidden") === "true") return;
    if (tag === "BR") { out += "\n"; return; }
    const block = /^(P|DIV|H[1-6]|LI|UL|OL|PRE|BLOCKQUOTE|TABLE|TR|SECTION)$/.test(tag);
    if (block) nl();
    if (tag === "LI") {
      const list = n.parentElement;
      out += list && list.tagName === "OL" ? `${[...list.children].indexOf(n) + 1}. ` : "• ";
    }
    if (tag === "TD" || tag === "TH") out += out.endsWith("\n") ? "| " : " | ";
    for (const c of n.childNodes) walk(c);
    if (block) nl();
    if (/^(P|H[1-6]|PRE|UL|OL|TABLE|BLOCKQUOTE)$/.test(tag)) out += "\n";
  };
  walk(root);
  return out.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function replyText(item) {
  const msg = item.querySelector(SEL.assistant);
  if (!msg) return { text: "", done: false };
  const parts = [...msg.children].filter((c) => !c.querySelector(SEL.thinking) && !c.matches(SEL.thinking));
  const text = parts.map(toText).filter(Boolean).join("\n\n");
  const done = msg.dataset.streamingComplete === "true" || msg.dataset.streamingState === "DONE";
  return { text, done };
}

async function watchReply(before, requestId) {
  const item = await waitFor(() => {
    const items = [...document.querySelectorAll(SEL.item)].filter((e) => e.dataset.messageRole === "assistant" && !before.has(e.dataset.messageId));
    return items[items.length - 1];
  }, 30000, 200);
  if (!item) {
    post({ type: "reply", requestId, state: "error", error: "Meta AI didn't start a reply" });
    return;
  }
  const end = Date.now() + REPLY_TIMEOUT_MS;
  let last = "";
  while (Date.now() < end) {
    const { text, done } = replyText(item);
    if (text !== last) {
      last = text;
      if (!done) post({ type: "reply", requestId, state: "streaming", text, messageId: item.dataset.messageId });
    }
    if (done && text) {
      post({ type: "reply", requestId, state: "done", text, messageId: item.dataset.messageId, conversationId: conversationId() });
      return;
    }
    await sleep(300);
  }
  post({ type: "reply", requestId, state: "error", error: "Meta AI's reply didn't finish in time", text: last });
}

// -- messages from the side panel ----------------------------------------------------------

chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (msg.type === "status") {
    respond({ conversationId: conversationId(), composer: !!document.querySelector(SEL.composer), shieldOn, url: location.href });
    return false;
  }
  if (msg.type === "send") {
    (async () => {
      const before = assistantIds();
      await placeText(msg.text);
      await pressSend();
      respond({ ok: true });
      watchReply(before, msg.requestId);
    })().catch((e) => respond({ ok: false, error: e.message }));
    return true; // respond asynchronously
  }
  return false;
});

// meta.ai is a single-page app: report conversation changes (a new chat gets its id after the first send).
let lastConversation = conversationId();
setInterval(() => {
  const id = conversationId();
  if (id !== lastConversation) {
    lastConversation = id;
    post({ type: "url", conversationId: id });
  }
}, 400);
