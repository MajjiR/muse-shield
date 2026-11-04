"""Tools agents may call, and per-argument rules for what the executor may unmask.

An argument's `resolve` set lists the placeholder types the executor may turn back into
real values for that argument. Anything else stays a placeholder, or the call is refused
if the type is forbidden. Recipient arguments only accept people or contacts already in
the vault: a literal address written by a model is refused, so injected text can't make
an agent send data to an address of its choosing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CONTENT_TYPES = {"PERSON", "ORG", "ADDRESS", "LOCATION", "AMOUNT", "PROJECT", "DATE", "CONTEXT"}  # CONTEXT = any block
NEVER = {"SECRET", "ID"}  # never leave the vault through a tool, whatever the tool


@dataclass(frozen=True)
class Param:
    name: str
    kind: str  # recipients | text | string | datetime | channel | telegram_chat
    required: bool = True
    resolve: frozenset[str] = frozenset()  # placeholder types the executor may unmask here
    description: str = ""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: tuple[Param, ...]
    side_effect: bool  # True: the user confirms a preview with real values before it runs
    external: bool = True  # True: arguments leave the device when it runs
    tags: tuple[str, ...] = field(default_factory=tuple)
    reads_private: bool = False  # True: its result holds new private data, so the masker runs on it before any agent sees it
    trusted_source: bool = False  # True: data you keep yourself (your contacts), so addresses in it may be recipients

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def schema(self) -> dict:
        """What the planning model sees: names, kinds and descriptions only."""
        return {"name": self.name, "description": self.description,
                "params": {p.name: {"kind": p.kind, "required": p.required, "description": p.description} for p in self.params}}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("send_email", "Send an email on the user's behalf.", (
        Param("to", "recipients", resolve=frozenset({"PERSON", "CONTACT"}), description="one or more <PERSON_n> or <CONTACT_n>"),
        Param("subject", "text", resolve=frozenset(CONTENT_TYPES)),
        Param("body", "text", resolve=frozenset(CONTENT_TYPES)),
    ), side_effect=True),
    Tool("create_calendar_event", "Put a meeting on the user's calendar and invite people.", (
        Param("title", "text", resolve=frozenset(CONTENT_TYPES)),
        Param("attendees", "recipients", required=False, resolve=frozenset({"PERSON", "CONTACT"})),
        Param("start", "datetime", description="ISO 8601 or a <DATE_n>", resolve=frozenset({"DATE"})),
        Param("duration_minutes", "string", required=False),
        Param("location", "text", required=False, resolve=frozenset({"ADDRESS", "LOCATION"})),
    ), side_effect=True),
    Tool("save_note", "Save a private note in the user's local vault.", (
        Param("title", "text", resolve=frozenset(CONTENT_TYPES)),
        Param("body", "text", resolve=frozenset(CONTENT_TYPES)),
    ), side_effect=False, external=False),
    Tool("read_inbox", "Read the user's recent emails, newest first. Names, addresses and other details come back as placeholders.", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES | {"CONTACT"}),
              description="optional words, a <PERSON_n> or a <CONTACT_n> to filter by"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("search_contacts", "Look people up in the user's address book. Addresses found here can be used as recipients.", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES | {"CONTACT"}), description="a name, company or <PERSON_n>"),
    ), side_effect=False, external=False, reads_private=True, trusted_source=True),
    Tool("list_events", "List the user's calendar events, soonest first. Each has an id for reschedule_event.", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES), description="optional words to filter by"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("reschedule_event", "Move a calendar event to a new time.", (
        Param("event_id", "string", description="the id from list_events"),
        Param("start", "datetime", description="new start, ISO 8601 or a <DATE_n>", resolve=frozenset({"DATE"})),
        Param("end", "datetime", required=False, resolve=frozenset({"DATE"})),
    ), side_effect=True),
    Tool("list_folder", "List what's in the user's documents folder, or in one of its subfolders. Every file and folder "
                        "has an id for read_file, query_table or list_folder.", (
        Param("folder_id", "string", required=False, description="a folder id from list_folder; leave out for the top"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("search_files", "Search every file in the user's documents folder (text, CSV, PDF, Word, PowerPoint).", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES), description="optional words to filter by"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("read_file", "Read one file. For a table you get its columns and a few sample rows; use query_table to "
                      "calculate over all of it.", (
        Param("file_id", "string", description="an id from list_folder or search_files"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("query_table", "Calculate over a CSV file, or every CSV in a folder (e.g. all monthly statements), on the "
                        "user's device. Totals come back as placeholders.", (
        Param("source_id", "string", description="a table or folder id from list_folder"),
        Param("operation", "string", description="sum, average, count, min or max"),
        Param("column", "string", required=False, description="the column to add up (not needed for count)"),
        Param("contains", "text", required=False, resolve=frozenset(CONTENT_TYPES),
              description="keep only rows containing these words, e.g. 'debit' or a placeholder like <ORG_1>"),
        Param("contains_column", "string", required=False, description="look for `contains` only in this column"),
        Param("month", "string", required=False, description="keep only rows dated in this month, e.g. 2026-10"),
        Param("group_by", "string", required=False, description="a column to total separately for each value, e.g. description"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("read_transactions", "Read the user's latest bank statement (date, description, amount, balance).", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES), description="e.g. a merchant, 'debit' or '2026-10'"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("read_health_records", "Read the user's medical reports, newest first.", (
        Param("query", "text", required=False, resolve=frozenset(CONTENT_TYPES), description="optional words to filter by"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("read_channel", "Read recent messages in one of the user's team chat channels.", (
        Param("channel", "channel", description="e.g. #finance"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("post_message", "Post a message in one of the user's team chat channels.", (
        Param("channel", "channel", description="e.g. #finance"),
        Param("text", "text", resolve=frozenset(CONTENT_TYPES)),
    ), side_effect=True),
    Tool("compute", "Do arithmetic on hidden amounts on the user's device, e.g. \"<SALARY_1> * 12 - <LOAN_1>\" or "
                    "\"<AMOUNT_1> > <AMOUNT_2>\". You get the answer back as a new placeholder (or yes/no for a comparison).", (
        Param("expression", "text", resolve=frozenset({"AMOUNT"}), description="numbers, amount placeholders, + - * / % ( ), "
                                                                            "comparisons, min/max/sum/abs/round"),
        Param("unit", "string", required=False, description="money (default when amounts are involved), percent or number"),
    ), side_effect=False, external=False),
    Tool("read_telegram", "Read the user's Telegram: with no chat_id, their recent chats; with a chat_id, that chat's "
                          "latest messages. Only works once Telegram is connected.", (
        Param("chat_id", "string", required=False, description="an id from the chat list"),
    ), side_effect=False, external=False, reads_private=True),
    Tool("send_telegram", "Send a Telegram message, as the user, to one of their chats.", (
        Param("chat_id", "telegram_chat", description="an id from read_telegram's chat list"),
        Param("text", "text", resolve=frozenset(CONTENT_TYPES)),
    ), side_effect=True),
    Tool("web_search", "Search the public web. The query leaves the device, so it stays masked, except a value the user "
                       "has already chosen to share in full in this chat (ask with NEED_CONTEXT first).", (
        Param("query", "text"),
    ), side_effect=False),
]}


def catalog() -> list[dict]:
    """Tool schemas for the planning model. Channel names are workspace structure, not personal data, so they're listed."""
    from ..connectors.personal import workspace

    out = []
    for t in TOOLS.values():
        schema = t.schema()
        if any(p.kind == "channel" for p in t.params):
            try:
                schema["description"] += f" The user's channels: {', '.join(workspace())}."
            except (OSError, ValueError, KeyError):
                pass  # no chat workspace configured
        out.append(schema)
    return out
