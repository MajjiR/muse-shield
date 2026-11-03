# Muse Shield for Meta AI (Chrome extension)

Muse Shield replaces meta.ai's message box with its own, an extension frame the page can't
read. Your message is masked on your device, only placeholders go into meta.ai, and Meta AI's
reply is restored in frames inside the chat. meta.ai's page never holds a real value.

```
composer frame (your text) --127.0.0.1--> engine: Muse Spark analysis + vault --> masked text
masked text --content.js--> meta.ai's real box (invisible, under the frame) --> Send
Meta AI reply (masked) --content.js--> composer --> engine: restore / NEED_CONTEXT ask
restored reply --chrome.storage.session--> reply frame inside the chat
```

- **The first message of each chat** carries a short privacy note (`PREAMBLE` in
  `muse_shield/app/extension.py`). It tells Meta AI to keep `<TYPE_n>` placeholders verbatim, and
  to reply `NEED_CONTEXT: <LABEL> <shape|summary|full> <reason>` when it needs hidden content.
- **Underlines while you type, Grammarly-style** (`/ext/preview`, nothing stored). Click one to
  keep it or mask it; select text to mask what the model missed. Names, IDs, contacts, secrets
  and addresses are always masked.
- **A `NEED_CONTEXT` reply becomes a consent card** in the chat. Pick a level, see exactly what
  would be sent, then Allow & send or Deny. The note goes to Meta AI as the next message.
- **meta.ai's own box is hidden under the Muse Shield composer** while the shield is on, and
  typed keys, paste, drop and dictation into it are blocked. The toolbar icon turns the shield
  on and off.
- **One vault chat per meta.ai conversation** (`/prompt/<id>`), bound in `extension.db` next to
  the vault. A new chat is bound once meta.ai assigns its id.

## Run

1. Start the engine. Fake data only: analysis sends raw text to Muse Spark Standard.
   ```bash
   MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.app   # PORT=8767 if 8765 is taken
   ```
   The extension finds the engine on 127.0.0.1 ports 8765–8769.
2. In `chrome://extensions`, turn on Developer mode, click **Load unpacked** and pick this
   folder.
3. Open https://www.meta.ai/ (signed in). The Muse Shield box replaces meta.ai's input.

## Files

| file | does |
|---|---|
| `content.js` | runs on meta.ai: places the frames, pastes masked text, presses Send, reads replies (`data-message-role`, `data-testid="assistant-message"`, `data-streaming-complete`) |
| `composer.*` | the input frame: underlines, keep/mask choices, sending, reply handling, consent |
| `reply.*` | one restored reply (or consent card) inside the chat; data from `chrome.storage.session` |
| `shared.js`, `frames.css` | engine discovery, API calls, rendering helpers and styles for both frames |
| `background.js` | tells frames their tab id; the toolbar icon toggles the shield |

Content scripts can't reach 127.0.0.1 and never receive real values. Only the frames, which run
on the extension's own origin, talk to the engine; meta.ai's scripts can't read inside them.
