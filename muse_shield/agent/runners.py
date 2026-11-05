"""What each tool actually does once the user has confirmed it. These see real values.

With Google connected (Connections in the app), email and calendar go through your Gmail and
Google Calendar. Otherwise email goes over SMTP when MUSE_SHIELD_SMTP_HOST is set, else it's
kept in the vault's encrypted outbox only, so prototyping never sends real mail by accident.
"""

from __future__ import annotations

import json
import os
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from ..app.vault import Vault
from ..connectors import SAMPLES, data_path
from ..connectors import folder, google, personal, telegram
from ..connectors.compute import compute


def send_email(vault: Vault, chat_id: str, args: dict) -> dict:
    if google.connected(vault):
        sent = google.send_email(vault, args)
        vault.add_outbox(chat_id, "send_email", {"to": args["to"], "subject": args["subject"], "body": args["body"],
                                                 "message_id": sent["message_id"], "delivered": True, "via": "gmail"})
        return sent
    msg = EmailMessage()
    msg["From"] = os.environ.get("MUSE_SHIELD_SMTP_FROM", "me@localhost")
    msg["To"] = ", ".join(args["to"])
    msg["Subject"] = args["subject"]
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@muse-shield>"
    msg.set_content(args["body"])
    host = os.environ.get("MUSE_SHIELD_SMTP_HOST")
    delivered = False
    if host:
        with smtplib.SMTP(host, int(os.environ.get("MUSE_SHIELD_SMTP_PORT", "587")), timeout=30) as smtp:
            smtp.starttls()
            if os.environ.get("MUSE_SHIELD_SMTP_USER"):
                smtp.login(os.environ["MUSE_SHIELD_SMTP_USER"], os.environ.get("MUSE_SHIELD_SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        delivered = True
    outbox_id = vault.add_outbox(chat_id, "send_email", {"to": args["to"], "subject": args["subject"], "body": args["body"],
                                                         "message_id": msg["Message-ID"], "delivered": delivered})
    return {"status": "sent" if delivered else "saved to outbox (SMTP not configured)", "to": args["to"],
            "subject": args["subject"], "outbox_id": outbox_id}


def create_calendar_event(vault: Vault, chat_id: str, args: dict) -> dict:
    if google.connected(vault):
        made = google.create_event(vault, args)
        vault.add_outbox(chat_id, "create_calendar_event", {**args, "via": "google", "link": made["link"]})
        return {k: v for k, v in made.items() if k != "link"}
    try:
        start = datetime.fromisoformat(args["start"])
    except ValueError:
        start = None
    minutes = int(args.get("duration_minutes") or 30)
    stamp = lambda d: d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
    ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Muse Shield//EN", "BEGIN:VEVENT", f"UID:{uuid.uuid4().hex}@muse-shield",
           f"SUMMARY:{args['title']}"]
    if start:
        ics += [f"DTSTART:{stamp(start)}", f"DTEND:{stamp(start + timedelta(minutes=minutes))}"]
    ics += [f"ATTENDEE:mailto:{a}" for a in args.get("attendees") or []]
    if args.get("location"):
        ics.append(f"LOCATION:{args['location']}")
    ics += ["END:VEVENT", "END:VCALENDAR"]
    outbox_id = vault.add_outbox(chat_id, "create_calendar_event", {**args, "ics": "\r\n".join(ics)})
    return {"status": "event created", "title": args["title"], "start": args["start"], "attendees": args.get("attendees") or [],
            "outbox_id": outbox_id}


def save_note(vault: Vault, chat_id: str, args: dict) -> dict:
    return {"status": "saved", "title": args["title"], "note_id": vault.add_outbox(chat_id, "save_note", args)}


def web_search(vault: Vault, chat_id: str, args: dict) -> dict:
    # Prototype: no outbound search. The point here is that the query stayed masked.
    return {"status": "search disabled in the prototype", "query": args["query"], "results": []}


MOCK_INBOX = SAMPLES / "inbox.json"  # invented mail, including one prompt-injection attempt


def read_inbox(vault: Vault, chat_id: str, args: dict) -> dict:
    if google.connected(vault):
        return google.read_inbox(vault, args)
    """Prototype mailbox: a JSON file (MUSE_SHIELD_INBOX or MUSE_SHIELD_DATA_DIR, else the bundled sample). IMAP slots in here."""
    mails = json.loads(data_path("inbox.json", "MUSE_SHIELD_INBOX").read_text())
    words = (args.get("query") or "").casefold().split()
    hits = [m for m in mails if all(w in " ".join((m["from"], m["subject"], m["body"])).casefold() for w in words)]
    hits.sort(key=lambda m: m["date"], reverse=True)
    return {"status": f"{len(hits[:10])} of {len(mails)} emails", "messages": hits[:10]}


RUNNERS = {"send_email": send_email, "create_calendar_event": create_calendar_event, "save_note": save_note,
           "read_inbox": read_inbox, "web_search": web_search, "compute": compute,
           **{name: getattr(personal, name) for name in ("search_contacts", "list_events", "reschedule_event",
                                                         "read_transactions", "read_health_records", "read_channel",
                                                         "post_message")},
           **{name: getattr(folder, name) for name in ("list_folder", "search_files", "read_file", "query_table")},
           "read_telegram": telegram.read_telegram, "send_telegram": telegram.send_telegram}
