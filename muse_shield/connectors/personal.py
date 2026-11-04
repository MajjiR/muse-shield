"""Contacts (vCard), calendar (iCalendar), files (a folder), bank statement (CSV) and health records (a folder).

Reads return {"status": ..., "<records>": [...]} with each record's text in one field, ready for masking.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from ..app.vault import Vault
from . import data_path, matches, opaque_id

MAX_RECORDS = 10
MAX_TEXT = 2000  # characters of a file or report the model gets; each paragraph costs one masking call


# -- contacts --------------------------------------------------------------------------------
def _vcards(path: Path) -> list[dict]:
    cards, card = [], None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line == "BEGIN:VCARD":
            card = {"emails": [], "phones": []}
        elif line == "END:VCARD" and card is not None:
            cards.append(card)
            card = None
        elif card is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";")[0].upper()
            if key == "FN":
                card["name"] = value
            elif key == "ORG":
                card["org"] = value.replace(";", " ").strip()
            elif key == "EMAIL":
                card["emails"].append(value)
            elif key == "TEL":
                card["phones"].append(value)
    return cards


def search_contacts(vault: Vault, chat_id: str, args: dict) -> dict:
    cards = _vcards(data_path("contacts.vcf", "MUSE_SHIELD_CONTACTS"))
    hits = [c for c in cards if matches(args.get("query"), c.get("name", ""), c.get("org", ""), *c["emails"])]
    out = []
    for c in hits[:MAX_RECORDS]:
        parts = [c.get("name", "")] + [f"<{e}>" for e in c["emails"]] + c["phones"] + ([c["org"]] if c.get("org") else [])
        out.append({"id": opaque_id(c.get("name", ""), *c["emails"]), "card": " ".join(p for p in parts if p)})
    return {"status": f"{len(out)} of {len(cards)} contacts", "contacts": out}


# -- calendar --------------------------------------------------------------------------------
def _ics_time(value: str) -> str:
    try:
        when = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return value
    return when.astimezone().isoformat(timespec="minutes")


def _events(text: str) -> list[dict]:
    events, ev = [], None
    for raw in text.replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            ev = {"attendees": []}
        elif line == "END:VEVENT" and ev is not None:
            events.append(ev)
            ev = None
        elif ev is not None and ":" in line:
            head, value = line.split(":", 1)
            key, *params = head.split(";")
            if key == "ATTENDEE":
                cn = next((p.split("=", 1)[1] for p in params if p.upper().startswith("CN=")), "")
                addr = value.removeprefix("mailto:")
                ev["attendees"].append(f"{cn} <{addr}>".strip() if cn else addr)
            elif key in ("UID", "SUMMARY", "LOCATION", "DESCRIPTION"):
                ev[key.lower()] = value
            elif key in ("DTSTART", "DTEND"):
                ev[key.lower()] = _ics_time(value)
    return events


def list_events(vault: Vault, chat_id: str, args: dict) -> dict:
    """Your calendar file plus events created or moved here (they live in the encrypted outbox)."""
    events = _events(data_path("calendar.ics", "MUSE_SHIELD_CALENDAR").read_text())
    moved = {}
    for item in vault.outbox():
        if item["tool"] == "create_calendar_event":
            events += _events(item["payload"].get("ics", ""))
        elif item["tool"] == "reschedule_event":
            moved[item["payload"]["event_id"]] = item["payload"]
    out = []
    for ev in events:
        eid = opaque_id(ev.get("uid", ""), ev.get("summary", ""))
        if eid in moved:
            ev["dtstart"], ev["dtend"] = moved[eid]["start"], moved[eid].get("end") or ev.get("dtend")
        text = " · ".join(p for p in [ev.get("summary", ""), ("with " + ", ".join(ev["attendees"])) if ev["attendees"] else "",
                                      ev.get("location", "")] if p)
        if matches(args.get("query"), text):
            out.append({"id": eid, "start": ev.get("dtstart", ""), "end": ev.get("dtend", ""), "event": text})
    out.sort(key=lambda e: e["start"])
    return {"status": f"{len(out[:MAX_RECORDS])} events", "events": out[:MAX_RECORDS]}


def reschedule_event(vault: Vault, chat_id: str, args: dict) -> dict:
    found = [e for e in list_events(vault, chat_id, {})["events"] if e["id"] == args["event_id"]]
    if not found:
        raise ValueError(f"no event with id {args['event_id']}")
    outbox_id = vault.add_outbox(chat_id, "reschedule_event", {"event_id": args["event_id"], "event": found[0]["event"],
                                                               "from": found[0]["start"], "start": args["start"],
                                                               "end": args.get("end", "")})
    return {"status": "event moved", "event": found[0]["event"], "start": args["start"], "outbox_id": outbox_id}


# -- files -----------------------------------------------------------------------------------
def _files() -> list[Path]:
    folder = data_path("files", "MUSE_SHIELD_FILES")
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in (".md", ".txt") and p.is_file())


def search_files(vault: Vault, chat_id: str, args: dict) -> dict:
    out = []
    for p in _files():
        text = p.read_text()
        if matches(args.get("query"), p.stem.replace("_", " "), text):
            out.append({"id": opaque_id(p.name), "name": p.stem.replace("_", " "), "excerpt": text[:400]})
    return {"status": f"{len(out[:MAX_RECORDS])} files", "files": out[:MAX_RECORDS]}


def read_file(vault: Vault, chat_id: str, args: dict) -> dict:
    for p in _files():
        if opaque_id(p.name) == args["file_id"]:
            text = p.read_text()
            return {"status": "read" + (" (trimmed)" if len(text) > MAX_TEXT else ""), "id": args["file_id"],
                    "name": p.stem.replace("_", " "), "text": text[:MAX_TEXT]}
    raise ValueError(f"no file with id {args['file_id']}")


# -- bank statement --------------------------------------------------------------------------
def read_transactions(vault: Vault, chat_id: str, args: dict) -> dict:
    with data_path("statement.csv", "MUSE_SHIELD_STATEMENT").open(newline="") as f:
        rows = list(csv.DictReader(f))
    hits = [r for r in rows if matches(args.get("query"), r["date"], r["description"], r["type"])]
    out = [{"id": opaque_id(r["date"], r["description"], r["amount"]), "date": r["date"],
            "entry": f"{r['description']} · {r['type']} ₹{_inr(r['amount'])} · balance ₹{_inr(r['balance'])}"} for r in hits]
    return {"status": f"{len(out)} transactions", "transactions": out}


def _inr(value: str) -> str:
    """'200000.00' -> '2,00,000.00' (Indian grouping, as on a statement)."""
    whole, _, frac = f"{float(value):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail]) + "." + frac


# -- health records --------------------------------------------------------------------------
def read_health_records(vault: Vault, chat_id: str, args: dict) -> dict:
    folder = data_path("health", "MUSE_SHIELD_HEALTH")
    out = []
    for p in sorted(folder.glob("*.txt"), reverse=True):
        text = p.read_text()
        if matches(args.get("query"), text):
            out.append({"id": opaque_id(p.name), "date": p.name[:10], "report": text[:MAX_TEXT]})
    return {"status": f"{len(out[:MAX_RECORDS])} reports", "reports": out[:MAX_RECORDS]}


# -- team chat -------------------------------------------------------------------------------
def workspace() -> dict:
    return json.loads(data_path("chat.json", "MUSE_SHIELD_CHAT").read_text())["channels"]


def channel_names() -> set[str]:
    """Your channel names, which tool descriptions list for the model, so masking leaves them alone."""
    try:
        return {n for name in workspace() for n in (name, name.lstrip("#"))}
    except (OSError, ValueError, KeyError):
        return set()


def read_channel(vault: Vault, chat_id: str, args: dict) -> dict:
    channels = workspace()
    name = args["channel"] if args["channel"].startswith("#") else "#" + args["channel"]
    if name not in channels:
        raise ValueError(f"no channel {name}; channels: {', '.join(channels)}")
    msgs = channels[name]["messages"][-MAX_RECORDS:]
    posted = [i["payload"] for i in vault.outbox() if i["tool"] == "post_message" and i["payload"]["channel"] == name]
    out = [{"id": m["id"], "ts": m["ts"], "message": f"{m['user']}: {m['text']}"} for m in msgs]
    out += [{"id": opaque_id(p["text"]), "ts": p.get("ts", ""), "message": f"You: {p['text']}"} for p in posted]
    return {"status": f"{len(out)} messages in {name}", "channel": name,
            "shared_outside": bool(channels[name].get("external")), "messages": out}


def post_message(vault: Vault, chat_id: str, args: dict) -> dict:
    name = args["channel"] if args["channel"].startswith("#") else "#" + args["channel"]
    if name not in workspace():
        raise ValueError(f"no channel {name}")
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    outbox_id = vault.add_outbox(chat_id, "post_message", {"channel": name, "text": args["text"], "ts": ts})
    return {"status": f"posted in {name} (kept here; no workspace is connected)", "channel": name, "outbox_id": outbox_id}
