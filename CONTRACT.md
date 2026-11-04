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
| `documents` | chat, number, format, status, size, pages, counts by type, warning codes; **encrypted** original file, masked copy and record (file name, extracted text, spans) |

## Local API (127.0.0.1:8765)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/mask` | `{text, chat_id?}` | `{chat_id, masked_text, spans[], contexts[], analysis_ok, error?, latency_ms, cost_usd}` |
| POST | `/unmask` | `{text, chat_id}` | `{text}` |
| POST | `/chat` | `{chat_id?, message, document_ids?}` | `{chat_id, message_id, reply, masked_reply, sent[], ask?, masked}` |
| POST | `/reveal` | `{ask_id, decision, level?}` | `{chat_id, reply?, ask?, revealed?}` |
| GET | `/chats` | | `[{chat_id, title, created_at, messages}]` |
| GET | `/chats/{id}` | | `{chat_id, messages[]}` (originals decrypted locally) |
| GET | `/chats/{id}/vault` | | `{entities[], contexts[]}` (labels only; values on `/vault/reveal`) |
| POST | `/vault/reveal` | `{chat_id, label}` | `{label, value}`: local only, logged |
| GET | `/chats/{id}/graph` | | `{nodes[], edges[]}`: labels and types only |
| GET | `/inspector` | | `{requests[], summary}`: every outbound byte |
| GET | `/metrics` | | counts by type, asks, consents, cost per chat |
| POST | `/documents` | raw file bytes, `content-type: application/octet-stream`, headers `x-filename` (percent-encoded), `x-chat-id?` | `Document` (status `analysing`) |
| GET | `/documents/{id}` | `?detail=true` | `Document`; detail adds `{text, masked_text, spans[], units[]}` (local only) |
| GET | `/documents/{id}/masked` | | the masked copy, same format; `409` unless it passed verification |
| GET | `/chats/{id}/documents` | | `[Document]` |
| POST | `/documents/{id}/delete` | | `{ok}` |

A **span** is `{start, end, text, type, role?, placeholder, kind: entity|context, source: model|policy|user}`.
An **ask** is `{ask_id, chat_id, label, kind, level, reason, preview}`; `preview` is exactly the
text that would be sent.

## Documents (PDF, .docx, .pptx)

1. **Upload** the file into a chat. The format is decided from the bytes. Encrypted, legacy
   (`.doc`, `.ppt`), macro-enabled and Strict files are refused (`415`); limits are 25 MB, 300 pages
   or slides, and 300,000 characters (`413`). Analysis must be on (`503` otherwise).
2. **Sanitize** what can't be masked reliably, before anything is sent: tracked changes (accepted),
   comments, field codes, links, pictures, charts, embedded objects, alt text, properties, thumbnails;
   for PDFs also annotations, forms, attachments, bookmarks, XMP and text outside the page. Each
   removal is a warning `{code, count, where?}`.
3. **Extract** every text node into one string, packed into analysis units of up to 800
   characters, and mask it with **one** `/mask`-style call (every occurrence of a found value is
   masked). Placeholders are shared with the chat.
4. **Write back** in the same format: the placeholder goes into the first run of each value, with its
   formatting; PDFs are truly redacted (text under the box removed, label written as selectable text).
   PDF pages with no readable text layer are emptied and marked **not checked**.
5. **Verify**: the copy is reopened and every channel searched for every masked value, passage
   sentence, original property value and the file name. Failures name the place and placeholder,
   never the value. Status becomes `ready` (copy downloadable) or `blocked` (no copy; the masked text
   can still be used in chat).

A **Document** is `{doc_id, chat_id, n, format, status: extracting|analysing|verifying|ready|blocked|failed,
bytes, pages, counts, warnings[], page_status[], verify?: {ok, checks, failures[], warnings[]},
progress?: {done, total}, filename, has_masked_copy, error?}`. `filename` is for the local UI only and
is never sent to a model.

**In chat**, `document_ids` attaches each document once, as its own message
`[Document n · format · pages, masked like the rest of this chat]` followed by its masked text; the
message may then be empty. The pre-send guard and `NEED_CONTEXT` apply as for any message.
`MUSE_SHIELD_DOC_CHAR_BUDGET` (default 200,000) caps the documents in one chat. `/chats/{id}` returns
document messages as `{role: "document", text: "", document: Document}`.
