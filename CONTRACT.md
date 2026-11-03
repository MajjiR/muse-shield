# Muse Shield contract

The engine and every client (web UI now, Mac/Electron app later) code against this file.
Don't change it without updating the schemas in `muse_shield/app/schemas.py`.

## Flow: two Muse Spark calls

1. **Analyze (call 1).** The engine sends the raw message, paragraph by paragraph, to Muse
   Spark with the analysis prompt (`muse_shield/backends.py`). Spark returns entities (text,
   type, role for amounts) and context blocks (sentence numbers, kind, summary). Code locates
   each entity by exact search and drops any it can't find. If analysis fails, **nothing is
   sent**.
2. **Mask.**
   - Entities become placeholders and their values go into the encrypted vault, under the chat.
   - A sentence run that a context covers becomes one block placeholder. The vault keeps the
     block's full text, **shape** (inner entities replaced by their placeholders, numbers by
     `[NUMBER]`) and **summary** (Spark's names-free one-liner).
3. **Answer (call 2).**
   - Muse Spark gets only masked text, plus a system prompt explaining the placeholders.
   - If it needs a hidden block or value, it replies with one line:
     `NEED_CONTEXT: <LABEL> <level> <reason>`, where level is `shape`, `summary` or `full`.
   - The engine turns that line into an **ask**. The UI shows exactly what would be revealed,
     and the user allows or denies it; the choice is logged in `consents`.
   - On allow, the revealed text goes into the next call, and the reply is retried once.
4. **Rehydrate.** Placeholders in the reply are replaced with real values locally.

**Development note:** call 1 sends raw text to Meta. Use fake data only until analysis moves
to a self-hosted model. Use Spark Standard, never Contributor (Contributor lets Meta train on
the prompts).

## Placeholders

- Format: `<TYPE_n>`; amounts use their role, `<ROLE_n>`; context blocks use their kind,
  `<KIND_n>`.
- Numbering is **per chat**, starting at 1. The same normalized value gets the same
  placeholder within a chat.
- The same value in two chats is **one entity**, linked by `value_hash`, with its own
  placeholder in each chat.

| Kind | Labels |
|---|---|
| entity | PERSON, ORG, ADDRESS, LOCATION, PROJECT, ID, CONTACT, DATE, SECRET, SENSITIVE_ATTRIBUTE |
| amount role | SALARY, PRICE, DEAL_VALUE, LOAN, REVENUE, BUDGET, FEE, AMOUNT (role OTHER) |
| context | DEAL, DECISION, PLAN, NEGOTIATION, PROJECT, HR |

**Hard rules** (run after the model; the model can't override them): PERSON, ID, CONTACT,
SECRET and ADDRESS are always masked.

## Scopes

`workspace → chat → message`. Placeholders are minted at chat scope, and values are resolved
chat first, then workspace.

## Vault (SQLite, values AES-256-GCM encrypted)

| Table | Holds |
|---|---|
| `scopes` | workspace / chat / message rows, title, parent |
| `entities` | type, `value_hash` = HMAC-SHA256(normalized value), encrypted value |
| `placeholders` | chat, label, entity or context, number |
| `contexts` | chat, label, kind, subtype; encrypted full text, shape and summary |
| `messages` | chat, role, masked text; encrypted original for user messages |
| `edges` | `appears_with` (entity ↔ entity in one message), `mentioned_in` (entity → context) |
| `audit` | event, chat, counts by type: **never values** |
| `consents` | chat, label, level, decision, reason, time |

## Local API (127.0.0.1:8765)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/mask` | `{text, chat_id?}` | `{chat_id, masked_text, spans[], contexts[], analysis_ok, error?, latency_ms, cost_usd}` |
| POST | `/unmask` | `{text, chat_id}` | `{text}` |
| POST | `/images/mask` | `{image (data: URL or base64), chat_id?, verify?}` | `{chat_id, image (PNG data URL), regions[] {kind, type, label, box, source}, masked_text, verify {ok, leaked[], faces_left, new_finds[]}, timings_ms, cost}` |
| POST | `/chat` | `{chat_id?, message}` | `{chat_id, message_id, reply, masked_reply, sent[], ask?, masked}` |
| POST | `/reveal` | `{ask_id, decision, level?}` | `{chat_id, reply?, ask?, revealed?}` |
| GET | `/chats` | | `[{chat_id, title, created_at, messages}]` |
| GET | `/chats/{id}` | | `{chat_id, messages[]}` (originals decrypted locally) |
| GET | `/chats/{id}/vault` | | `{entities[], contexts[]}` (labels only; values on `/vault/reveal`) |
| POST | `/vault/reveal` | `{chat_id, label}` | `{label, value}`: local only, logged |
| GET | `/chats/{id}/graph` | | `{nodes[], edges[]}`: labels and types only |
| GET | `/inspector` | | `{requests[], summary}`: every outbound byte |
| GET | `/metrics` | | counts by type, asks, consents, cost per chat |

A **span** is `{start, end, text, type, role?, placeholder, kind: entity|context, source: model|policy|user}`.
An **ask** is `{ask_id, chat_id, label, kind, level, reason, preview}`; `preview` is exactly the
text that would be sent.

## Images

`POST /images/mask` masks a picture before it goes anywhere:

1. **Muse Spark** (vision) reads the image: its text, each sensitive value with a box on its 0-1000
   grid, and faces, signatures, QR codes, barcodes, licence plates and ID photos.
2. **SAM 3.1** finds every `face` and `license plate` as pixel boxes (one request per concept).
3. **Refine:** for each value, Spark is asked again on a crop around its first box; if the two boxes
   disagree, both are covered.
4. Faces and ID photos get an oval blur; codes and plates are pixelated; values get a bar labelled
   with their **vault placeholder**, the same `<PERSON_1>` the value has in text chats.
5. **Re-scan:** the masked image goes back to Spark. Any masked value it can still read, or a face
   outside a blurred region, sets `verify.ok = false`.

Values are never in the response: regions carry labels, and the vault keeps the values. The
original image isn't stored. Like call 1 for text, this sends the raw image to Meta, so it's off
unless `MUSE_SHIELD_DEV_RAW_ANALYSIS=1`, and only for made-up images.
