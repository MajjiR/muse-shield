"""Check a placeholder tool call against the tool's rules and work out exactly what it unmasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..app.vault import Vault
from .tools import NEVER, TOOLS, Tool

LABEL = re.compile(r"<[A-Z][A-Z_]*_\d+>")
# Tools whose arguments may carry a real value you approved sharing in this chat. A web search is useless with a
# placeholder ("news about <ORG_1>"), so once you share the real name with Muse Spark it may search for it. Email,
# invites and posts still take placeholders: the device fills in real values itself.
SEARCH_WITH_APPROVED = {"web_search"}


def tool_allows_approved(where: str) -> bool:
    return where.split(".", 1)[0] in SEARCH_WITH_APPROVED
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


@dataclass
class Checked:
    tool: Tool
    masked: dict  # arguments as the model wrote them (placeholders)
    real: dict = field(default_factory=dict)  # arguments the tool will run with (local only)
    unmasked: list[str] = field(default_factory=list)  # labels this call reveals to the tool
    recipients: list[dict] = field(default_factory=list)  # {label, via, person, address}
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _type_of(vault: Vault, chat_id: str, label: str) -> str | None:
    t = vault.label_type(chat_id, label)
    if t is None:
        return None
    kind, typ = t
    return "CONTEXT" if kind == "context" else typ


def approved_labels(vault: Vault, chat_id: str) -> set[str]:
    """Labels you chose to share in full in this chat (the consent card's 'Share full text'), latest decision wins."""
    latest: dict[str, tuple[str, str]] = {}
    for c in vault.consents(chat_id):
        latest[c["label"]] = (c["decision"], c["level"])
    return {label for label, (decision, level) in latest.items() if decision == "allow" and level == "full"}


def _text(vault: Vault, chat_id: str, value: str, allowed: frozenset[str], where: str, out: Checked, external: bool,
          approved: set[str] = frozenset()) -> str:
    mapping = vault.mapping(chat_id)
    # A raw vault value written straight into an external argument is a leak the model shouldn't be able to cause,
    # unless you already chose to share that exact value in this chat (`approved`, web search only).
    if external:
        for label, real in mapping.items():
            # A date or time in a field that would receive the real date anyway (a calendar start) reveals nothing,
            # and short ones ("IST", "15:00") turn up in any timestamp the model writes around a placeholder.
            if "DATE" in allowed and _type_of(vault, chat_id, label) == "DATE":
                continue
            if len(real) >= 3 and real.casefold() in value.casefold() and label not in value and label not in approved:
                hint = " (or ask you to share it first)" if tool_allows_approved(where) else ""
                out.violations.append(f"{where}: contains the real value behind {label}; agents must use placeholders{hint}")

    def sub(m: re.Match) -> str:
        label = m.group(0)
        typ = _type_of(vault, chat_id, label)
        if typ is None:
            out.violations.append(f"{where}: {label} isn't in this chat's vault")
            return label
        if typ in NEVER:
            out.violations.append(f"{where}: {label} is a {typ}, which never leaves the vault")
            return label
        if typ in allowed:
            out.unmasked.append(label)
            return mapping[label]
        return label  # stays a placeholder for this tool

    return LABEL.sub(sub, value)


def _recipients(vault: Vault, chat_id: str, value, where: str, out: Checked) -> list[str]:
    items = value if isinstance(value, list) else [v.strip() for v in str(value).split(",") if v.strip()]
    addresses = []
    for item in items:
        labels = LABEL.findall(item)
        if not labels or LABEL.sub("", item).strip():
            out.violations.append(f"{where}: '{item}' isn't a placeholder; recipients must be people or contacts from your vault")
            continue
        label = written = labels[0]
        typ = _type_of(vault, chat_id, label)
        if typ == "CONTACT":
            if vault.from_tool(chat_id, label):
                out.violations.append(f"{where}: {label} came from a tool result (like an email you received), not from you; "
                                      "write the address yourself to send to it")
                continue
            address = vault.resolve(chat_id, label)
            person = None
        elif typ == "PERSON":
            emails = [c for c in vault.contacts_for(chat_id, label) if c["kind"] == "email"]
            yours = [c for c in emails if not vault.from_tool(chat_id, c["label"])]
            if not yours:
                out.violations.append(f"{where}: no email address is known for {label}" if not emails else
                                      f"{where}: the only address for {label} came from a tool result (like an email you "
                                      "received), not from you; write the address yourself to send to it")
                continue
            address, person = yours[0]["value"], vault.resolve(chat_id, label)
            label = yours[0]["label"]
        else:
            out.violations.append(f"{where}: {label} is a {typ or 'unknown placeholder'}, not a person or contact")
            continue
        if not address or not EMAIL.fullmatch(address):
            out.violations.append(f"{where}: {label} isn't an email address")
            continue
        out.unmasked.append(label)
        # For the user's preview only (agents never get recipients): what the model wrote, the contact used, the real name.
        out.recipients.append({"label": written, "via": label, "person": person, "address": address})
        addresses.append(address)
    return addresses


def check(vault: Vault, chat_id: str, tool_name: str, args: dict) -> Checked:
    tool = TOOLS.get(tool_name)
    if tool is None:
        c = Checked(TOOLS["save_note"], args)
        c.violations.append(f"unknown tool '{tool_name}'")
        return c
    out = Checked(tool, dict(args))
    for name in args:
        if tool.param(name) is None:
            out.violations.append(f"unknown argument '{name}' for {tool.name}")
    for p in tool.params:
        if p.name not in args or args[p.name] in (None, "", []):
            if p.required:
                out.violations.append(f"missing required argument '{p.name}'")
            continue
        value = args[p.name]
        where = f"{tool.name}.{p.name}"
        if p.kind == "recipients":
            out.real[p.name] = _recipients(vault, chat_id, value, where, out)
        elif p.kind == "channel":
            out.real[p.name] = _channel(str(value), where, out)
        elif p.kind == "telegram_chat":
            out.real[p.name] = _telegram_chat(vault, str(value), where, out)
        else:
            approved = approved_labels(vault, chat_id) if tool.name in SEARCH_WITH_APPROVED else frozenset()
            out.real[p.name] = _text(vault, chat_id, str(value), p.resolve, where, out, tool.external, approved)
    shared = [c for p, c in ((p, out.real.get(p.name)) for p in tool.params if p.kind == "channel") if c and _shared_outside(c)]
    if shared and tool.side_effect and out.unmasked:
        out.violations.append(f"{tool.name}: {shared[0]} is shared with people outside your workspace, so hidden values "
                              f"({', '.join(sorted(set(out.unmasked)))}) can't be posted there")
    out.unmasked = sorted(set(out.unmasked))
    return out


def _telegram_chat(vault: Vault, value: str, where: str, out: Checked) -> str:
    """Only a chat you already have (from the last read_telegram listing): never a username a message suggested."""
    from ..connectors.telegram import chat_info

    chat = chat_info(vault, value)
    if not chat:
        out.violations.append(f"{where}: '{value}' isn't one of your Telegram chats; list your chats first")
        return value
    kind = {"private": "private chat", "group": "group chat", "channel": "channel"}[chat["kind"]]
    out.recipients.append({"label": value, "via": "", "person": chat["title"], "address": f"Telegram · {kind}"})
    return value


def _channel(value: str, where: str, out: Checked) -> str:
    """A channel must be one of yours; the model can't invent a destination."""
    from ..connectors.personal import workspace

    name = value if value.startswith("#") else "#" + value
    if LABEL.search(name) or name not in workspace():
        out.violations.append(f"{where}: '{value}' isn't one of your channels")
    return name


def _shared_outside(name: str) -> bool:
    from ..connectors.personal import workspace

    return bool(workspace().get(name, {}).get("external"))
