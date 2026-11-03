// One restored Meta AI reply, shown inside meta.ai's chat in place of the masked text.
// Data comes from chrome.storage.session (extension-only), never from the page.

const messageId = decodeURIComponent(location.hash.slice(1));
const key = `r:${messageId}`;
const HINTS = { shape: "structure, details still masked", summary: "a one-line gist", full: "the real text" };
let tabId = null;
let showMasked = false;

function header(data) {
  const h = el("div", "rhead");
  h.append(el("span", "rbadge", data.state === "ask" || data.state === "answered" ? "🛡️ Muse Shield · Meta AI asked for hidden context" : "🛡️ Restored on your device"));
  if (data.masked) {
    const t = el("button", "link", showMasked ? "Show restored" : "What Meta AI saw");
    t.onclick = () => { showMasked = !showMasked; render(data); };
    h.append(t);
  }
  return h;
}

function askCard(data) {
  const { ask } = data;
  const card = el("div", `ask ${data.state === "answered" ? (data.decision === "allow" ? "ask--allowed" : "ask--denied") : ""}`);
  const title = el("div", "ask__title");
  title.append("Meta AI wants to see ", el("code", "ph", ask.label));
  card.append(title);
  if (ask.reason) card.append(el("div", "muted small", `“${ask.reason}”`));
  let level = data.level || ask.level;
  const preview = el("pre", "ask__preview");
  const show = () => { preview.textContent = ask.previews[level]; };
  const levels = Object.keys(ask.previews);
  if (levels.length > 1) {
    const box = el("div", "ask__levels");
    for (const lv of levels) {
      const lab = el("label", "level");
      const r = el("input");
      r.type = "radio";
      r.name = "level";
      r.checked = lv === level;
      r.disabled = data.state === "answered";
      r.onchange = () => { level = lv; show(); };
      lab.append(r, ` ${lv} `, el("span", "muted small", `(${HINTS[lv]})`));
      box.append(lab);
    }
    card.append(box);
  }
  show();
  card.append(el("div", "muted small", "Exactly this would be sent:"), preview);
  if (data.state === "answered") {
    card.append(el("div", "muted small", data.decision === "allow" ? `You allowed ${ask.label} (${level}).` : `You declined ${ask.label}.`));
    return card;
  }
  const row = el("div", "ask__actions");
  const allow = el("button", "chip chip--accent", "Allow & send");
  const deny = el("button", "chip", "Deny");
  const answer = (decision) => {
    allow.disabled = deny.disabled = true;
    chrome.runtime.sendMessage({ type: "consent", tabId, messageId, decision, level }).catch(() => {});
  };
  allow.onclick = () => answer("allow");
  deny.onclick = () => answer("deny");
  row.append(allow, deny);
  card.append(row);
  return card;
}

function render(data) {
  const root = document.getElementById("root");
  root.replaceChildren();
  if (!data) return;
  root.append(header(data));
  if (showMasked) root.append(maskedNode(data.masked));
  else if (data.state === "ask" || data.state === "answered") root.append(askCard(data));
  else {
    const body = segmentsNode(data.segments);
    if (data.state === "streaming") body.append(el("span", "caret", "▍"));
    root.append(body);
    if (data.note) root.append(el("div", "muted small", data.note));
  }
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "session" && changes[key]) render(changes[key].newValue);
});

(async () => {
  tabId = await myTabId();
  render((await chrome.storage.session.get(key))[key]);
  reportHeight(tabId, { type: "reply-height", messageId });
})();
