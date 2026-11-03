// Frames inside meta.ai ask which tab they're in (tabs.getCurrent can come back empty in a frame).
chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  if (msg.type === "whoami") respond({ tabId: sender.tab ? sender.tab.id : null });
  return false;
});

// The toolbar icon toggles the shield.
chrome.action.onClicked.addListener(async () => {
  const { shieldOn = true } = await chrome.storage.local.get("shieldOn");
  await chrome.storage.local.set({ shieldOn: !shieldOn });
});
