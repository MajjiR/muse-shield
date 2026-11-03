"""What each tool actually does once the user has confirmed it. These see real values.

Email goes over SMTP when MUSE_SHIELD_SMTP_HOST is set; otherwise it's kept in the
vault's encrypted outbox only, so prototyping never sends real mail by accident.
"""

from __future__ import annotations

import os
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from ..app.vault import Vault


def send_email(vault: Vault, chat_id: str, args: dict) -> dict:
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


RUNNERS = {"send_email": send_email, "create_calendar_event": create_calendar_event, "save_note": save_note, "web_search": web_search}
