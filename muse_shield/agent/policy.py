"""Check a placeholder tool call against the tool's rules and work out exactly what it unmasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..app.vault import Vault
from .tools import NEVER, TOOLS, Tool

LABEL = re.compile(r"<[A-Z][A-Z_]*_\d+>")
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


def _text(vault: Vault, chat_id: str, value: str, allowed: frozenset[str], where: str, out: Checked, external: bool) -> str:
    mapping = vault.mapping(chat_id)
    # A raw vault value written straight into an external argument is a leak the model shouldn't be able to cause.
    if external:
        for label, real in mapping.items():
            if len(real) >= 3 and real.casefold() in value.casefold() and label not in value:
                out.violations.append(f"{where}: contains the real value behind {label}; agents must use placeholders")

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
            address = vault.resolve(chat_id, label)
            person = None
        elif typ == "PERSON":
            emails = [c for c in vault.contacts_for(chat_id, label) if c["kind"] == "email"]
            if not emails:
                out.violations.append(f"{where}: no email address is known for {label}")
                continue
            address, person = emails[0]["value"], vault.resolve(chat_id, label)
            label = emails[0]["label"]
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
        else:
            out.real[p.name] = _text(vault, chat_id, str(value), p.resolve, where, out, tool.external)
    out.unmasked = sorted(set(out.unmasked))
    return out
