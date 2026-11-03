# Muse Shield for Meta AI (Chrome extension)

You type in the Muse Shield side panel instead of meta.ai's own box. Your message is masked
on your device, only placeholders go into meta.ai, and Meta AI's reply is restored in the
side panel. meta.ai's page never holds a real value.

```
side panel (your text) --127.0.0.1--> engine: Muse Spark analysis + vault --> masked text
masked text --content.js--> meta.ai composer --> Send
Meta AI reply (masked) --content.js--> side panel --> engine: restore / NEED_CONTEXT ask
```

- **The first message of each chat** carries a short privacy note (`PREAMBLE` in
  `muse_shield/app/extension.py`). It tells Meta AI to keep `<TYPE_n>` placeholders verbatim, and
  to reply `NEED_CONTEXT: <LABEL> <shape|summary|full> <reason>` when it needs hidden content.
- **A `NEED_CONTEXT` reply becomes a consent card** in the panel. Pick a level, see exactly what
  would be sent, then Allow & send or Deny. The note goes to Meta AI as the next message.
- **meta.ai's own composer is locked while the shield is on**: an overlay covers it, and typed
  keys, paste, drop and dictation are blocked.
- **One vault chat per meta.ai conversation** (`/prompt/<id>`), bound in `extension.db` next to
  the vault. A new chat is bound once meta.ai assigns its id.

## Run

1. Start the engine. Fake data only: analysis sends raw text to Muse Spark Standard.
   ```bash
   MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.app   # PORT=8767 if 8765 is taken
   ```
   The panel finds the engine on 127.0.0.1 ports 8765–8769.
2. In `chrome://extensions`, turn on Developer mode, click **Load unpacked** and pick this
   folder.
3. Open https://www.meta.ai/ (signed in) and click the Muse Shield toolbar icon to open the
   side panel.

## Files

| file | does |
|---|---|
| `content.js` | runs on meta.ai: locks the composer, pastes masked text, presses Send, reads replies (`data-message-role`, `data-testid="assistant-message"`, `data-streaming-complete`) |
| `panel.*` | side panel: your chat with real values, the masked text Meta AI saw, consent cards |
| `background.js` | opens the side panel from the toolbar icon or the lock's button |

Content scripts can't reach 127.0.0.1 and never receive real values. Only the panel, which
runs on the extension's own origin, talks to the engine.
