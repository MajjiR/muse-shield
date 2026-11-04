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
    kind: str  # recipient | recipients | text | string | datetime
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
    Tool("web_search", "Search the public web. The query leaves the device, so it stays masked.", (
        Param("query", "text"),
    ), side_effect=False),
]}


def catalog() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]
