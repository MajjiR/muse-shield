// Muse Shield content script for meta.ai.
//
// It never sees a real value. It puts the Muse Shield composer (an extension frame the page
// can't read) exactly where meta.ai's message box is, pastes the masked text it's handed into
// meta.ai's real box, presses Send, reads Meta AI's reply back out, and shows restored replies
// in extension frames inside the chat.

const SEL = {
  composer: '[contenteditable="true"][data-testid="composer-input"]',
  send: '[data-testid="composer-send-button"]',
  item: "[data-message-item][data-message-role]",
  assistant: '[data-testid="assistant-message"]',
  thinking: '[data-testid="thinking-status"]',
};
const REPLY_TIMEOUT_MS = 180000;

let shieldOn = true;
let restoreOn = true; // off: meta.ai is shown exactly as Meta sees it
let inserting = false; // our own synthetic edits pass the lock
let composerHeight = 0;
const replies = new Map(); // meta.ai message id -> reported frame height (ids only)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const squash = (s) => (s || "").replace(/\s+/g, "");
const post = (msg) => chrome.runtime.sendMessage(msg).catch(() => {}); // frames may not be listening yet

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

// -- the Muse Shield composer over meta.ai's box ---------------------------------------------

const frame = document.createElement("iframe");
frame.className = "muse-shield-composer";
frame.src = chrome.runtime.getURL("composer.html");
frame.title = "Muse Shield";

const offPill = document.createElement("button");
offPill.className = "muse-shield-off";
offPill.type = "button";
offPill.textContent = "🛡️ Muse Shield is off · turn on";
offPill.addEventListener("click", () => chrome.storage.local.set({ shieldOn: true }));

function composerBox() {
  const ed = document.querySelector(SEL.composer);
  const send = document.querySelector(SEL.send);
  if (!ed) return null;
  let box = ed;
  while (box.parentElement && send && !box.contains(send)) box = box.parentElement;
  return box;
}

// The frame is hidden, never removed, while meta.ai re-renders its box (a new chat does that when
// it gets its id): removing an iframe reloads it, and the composer would forget its vault chat.
function place() {
  const box = composerBox();
  mountReplies();
  if (!shieldOn) {
    frame.remove();
    document.documentElement.appendChild(offPill);
    if (box) box.style.opacity = "";
    return;
  }
  offPill.remove();
  if (!box) {
    frame.style.visibility = "hidden";
    return;
  }
  frame.style.visibility = "";
  box.style.opacity = "0"; // the frame takes its place (opacity, not visibility: the box must stay focusable for our paste)
  const r = box.getBoundingClientRect();
  const height = Math.max(composerHeight, r.height + 4);
  Object.assign(frame.style, {
    left: `${r.left - 2}px`, width: `${r.width + 4}px`, height: `${height}px`, top: `${r.bottom + 2 - height}px`,
  });
  if (!frame.isConnected) document.documentElement.appendChild(frame);
}
setInterval(place, 250);
window.addEventListener("resize", place);

// Keystrokes, paste, drop and IME into meta.ai's real box are blocked while the shield is on
// (it autofocuses under the frame). Our own edits are synthetic and pass.
for (const type of ["beforeinput", "keydown", "keypress", "paste", "drop", "compositionstart"]) {
  window.addEventListener(type, (e) => {
    if (!shieldOn || inserting || !e.isTrusted) return;
    const ed = document.querySelector(SEL.composer);
    if (ed && e.target instanceof Node && ed.contains(e.target)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      frame.focus();
    }
  }, true);
}

chrome.storage.local.get({ shieldOn: true, restoreOn: true }).then((v) => { shieldOn = v.shieldOn; restoreOn = v.restoreOn; place(); });
chrome.storage.onChanged.addListener((c, area) => {
  if (area !== "local") return;
  if (c.shieldOn) shieldOn = c.shieldOn.newValue;
  if (c.restoreOn) {
    restoreOn = c.restoreOn.newValue;
    if (!restoreOn) unmountReplies();
  }
  place();
});

// -- restored replies inside the chat ------------------------------------------------------

// Your sent messages are covered the same way, so you see what you typed, not the masked text.
function mountReply(id) {
  if (!restoreOn) return;
  const item = document.querySelector(`[data-message-id="${CSS.escape(id)}"]`);
  if (!item) return;
  const user = item.dataset.messageRole === "user";
  const msg = user ? item : item.querySelector(SEL.assistant);
  if (!msg) return;
  for (const c of msg.children) {
    if (!c.classList.contains("muse-shield-reply") && (user || !c.querySelector(SEL.thinking))) c.setAttribute("data-muse-shield-hidden", "");
  }
  let f = msg.querySelector(":scope > iframe.muse-shield-reply");
  const column = composerBox();
  if (f && column) f.style.maxWidth = `${column.getBoundingClientRect().width}px`; // meta.ai's chat column
  if (!f) {
    f = document.createElement("iframe");
    f.className = "muse-shield-reply";
    f.title = "Restored by Muse Shield";
    f.src = chrome.runtime.getURL(`reply.html#${encodeURIComponent(id)}`);
    if (column) f.style.maxWidth = `${column.getBoundingClientRect().width}px`;
    msg.appendChild(f);
  }
  const h = replies.get(id);
  if (h) f.style.height = `${h}px`;
}

// React may re-render a message and drop our frame: put it back.
function mountReplies() {
  if (!restoreOn) return;
  for (const id of replies.keys()) mountReply(id);
}

function unmountReplies() {
  document.querySelectorAll("iframe.muse-shield-reply").forEach((f) => f.remove());
  document.querySelectorAll("[data-muse-shield-hidden]").forEach((e) => e.removeAttribute("data-muse-shield-hidden"));
}

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

function userIds() {
  return new Set([...document.querySelectorAll(SEL.item)].filter((e) => e.dataset.messageRole === "user").map((e) => e.dataset.messageId));
}

// The messages on the page as meta.ai shows them (masked), for restoring chats from before this tab.
function pageMessages() {
  return [...document.querySelectorAll(SEL.item)].map((e) => {
    const role = e.dataset.messageRole;
    const text = role === "assistant" ? replyText(e).text
      : [...e.children].filter((c) => !c.classList.contains("muse-shield-reply")).map(toText).join("\n");
    return { site_message_id: e.dataset.messageId, role, text };
  }).filter((m) => m.text);
}

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
    if (["BUTTON", "STYLE", "SCRIPT", "IFRAME", "svg", "SVG"].includes(tag) || n.getAttribute("aria-hidden") === "true") return;
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
  const parts = [...msg.children].filter((c) => !c.classList.contains("muse-shield-reply") && !c.querySelector(SEL.thinking) && !c.matches(SEL.thinking));
  const text = parts.map(toText).filter(Boolean).join("\n\n");
  const done = msg.dataset.streamingComplete === "true" || msg.dataset.streamingState === "DONE";
  return { text, done };
}

// The user message of the same turn (meta.ai gives both halves of a turn one data-turn-id).
function userIdFor(item) {
  const turn = item.dataset.turnId;
  const u = turn && document.querySelector(`[data-message-role="user"][data-turn-id="${CSS.escape(turn)}"]`);
  return u ? u.dataset.messageId : null;
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
      if (!done) post({ type: "reply", requestId, state: "streaming", text, messageId: item.dataset.messageId, userMessageId: userIdFor(item) });
    }
    if (done && text) {
      post({ type: "reply", requestId, state: "done", text, messageId: item.dataset.messageId, userMessageId: userIdFor(item),
             conversationId: conversationId() });
      return;
    }
    await sleep(300);
  }
  post({ type: "reply", requestId, state: "error", error: "Meta AI's reply didn't finish in time", text: last });
}

// -- messages from the Muse Shield frames --------------------------------------------------

chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (msg.type === "status") {
    respond({ conversationId: conversationId() });
    return false;
  }
  if (msg.type === "composer-height") {
    composerHeight = msg.height;
    place();
    return false;
  }
  if (msg.type === "mount-reply") {
    if (!replies.has(msg.messageId)) replies.set(msg.messageId, 0);
    mountReply(msg.messageId);
    return false;
  }
  if (msg.type === "reply-height") {
    replies.set(msg.messageId, msg.height);
    mountReply(msg.messageId);
    return false;
  }
  if (msg.type === "page-messages") {
    respond({ conversationId: conversationId(), messages: pageMessages() });
    return false;
  }
  if (msg.type === "send") {
    (async () => {
      const before = assistantIds();
      const beforeUsers = userIds();
      await placeText(msg.text);
      await pressSend();
      // Hide the masked bubble the moment meta.ai draws it; the composer covers it with what you typed.
      const mine = await waitFor(() => {
        const items = [...document.querySelectorAll(SEL.item)].filter((e) => e.dataset.messageRole === "user" && !beforeUsers.has(e.dataset.messageId));
        return items[items.length - 1];
      }, 4000, 40);
      if (mine && restoreOn) [...mine.children].forEach((c) => { if (!c.classList.contains("muse-shield-reply")) c.setAttribute("data-muse-shield-hidden", ""); });
      respond({ ok: true, userMessageId: mine ? mine.dataset.messageId : null });
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
    replies.clear();
    post({ type: "url", conversationId: id });
  }
}, 400);
