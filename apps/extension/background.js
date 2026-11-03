// Clicking the toolbar icon opens the side panel; the lock on meta.ai's composer can ask for it too.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === "open-panel" && sender.tab) chrome.sidePanel.open({ tabId: sender.tab.id }).catch(() => {});
});
