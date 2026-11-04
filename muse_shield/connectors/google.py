"""Google: one sign-in for Gmail, Calendar and Contacts.

The app ships one OAuth client of type "Desktop app" (MUSE_SHIELD_GOOGLE_CLIENT_FILE, the JSON Google
Cloud gives you, or MUSE_SHIELD_GOOGLE_CLIENT_ID / _SECRET). A desktop client's secret isn't
confidential, so the flow also uses PKCE, and Google sends the user back to this engine on the local
loopback address. The refresh token is kept encrypted in the vault, never in a file.

Every call here returns real values to the executor only; the tools around it mask reads and gate sends.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from ..app.vault import Vault

SCOPES = ["openid", "email",
          "https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/contacts.readonly"]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary"
PEOPLE = "https://people.googleapis.com/v1"
SECRET = "google"
PENDING_TTL = 600

client = httpx.Client(timeout=30)  # tests swap in a MockTransport client
_pending: dict[str, dict] = {}  # state -> {verifier, redirect_uri, at}


class GoogleError(RuntimeError):
    pass


def oauth_client() -> tuple[str, str] | None:
    """(client_id, client_secret) for the app's Desktop OAuth client, or None if it isn't set up."""
    path = os.environ.get("MUSE_SHIELD_GOOGLE_CLIENT_FILE")
    if path and Path(path).expanduser().exists():
        data = json.loads(Path(path).expanduser().read_text())
        cfg = data.get("installed") or data.get("web") or {}
        if cfg.get("client_id"):
            return cfg["client_id"], cfg.get("client_secret", "")
    if os.environ.get("MUSE_SHIELD_GOOGLE_CLIENT_ID"):
        return os.environ["MUSE_SHIELD_GOOGLE_CLIENT_ID"], os.environ.get("MUSE_SHIELD_GOOGLE_CLIENT_SECRET", "")
    return None


def status(vault: Vault) -> dict:
    saved = vault.secret(SECRET)
    return {"configured": oauth_client() is not None, "connected": bool(saved),
            "account": (saved or {}).get("email"), "services": ["Gmail", "Calendar", "Contacts"]}


def connected(vault: Vault) -> bool:
    return vault.secret(SECRET) is not None


# -- sign-in ---------------------------------------------------------------------------------
def start(redirect_uri: str) -> str:
    cfg = oauth_client()
    if not cfg:
        raise GoogleError("Google sign-in isn't set up in this build (no OAuth client)")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    now = time.time()
    for s in [s for s, p in _pending.items() if now - p["at"] > PENDING_TTL]:
        del _pending[s]
    _pending[state] = {"verifier": verifier, "redirect_uri": redirect_uri, "at": now}
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cfg[0], "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES),
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})


def finish(vault: Vault, code: str, state: str) -> dict:
    pending = _pending.pop(state, None)
    if not pending or time.time() - pending["at"] > PENDING_TTL:
        raise GoogleError("this sign-in link expired or was already used; start again")
    cid, csecret = oauth_client() or ("", "")
    r = client.post(TOKEN_URL, data={"code": code, "client_id": cid, "client_secret": csecret, "grant_type": "authorization_code",
                                     "redirect_uri": pending["redirect_uri"], "code_verifier": pending["verifier"]})
    if r.status_code != 200:
        raise GoogleError(f"Google refused the sign-in: {r.json().get('error_description') or r.text[:200]}")
    tok = r.json()
    if not tok.get("refresh_token"):
        raise GoogleError("Google didn't return a refresh token; remove Muse Shield from your Google account's "
                          "third-party access and connect again")
    email = client.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"}).json().get("email")
    saved = {"refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
             "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60, "email": email,
             "scopes": tok.get("scope", "").split()}
    vault.save_secret(SECRET, saved)
    vault.audit("connect", None, {"google": 1})
    return status(vault)


def disconnect(vault: Vault) -> None:
    saved = vault.secret(SECRET)
    if saved:
        try:
            client.post(REVOKE_URL, data={"token": saved["refresh_token"]})  # best effort: forget it here regardless
        except httpx.HTTPError:
            pass
    vault.delete_secret(SECRET)
    vault.audit("disconnect", None, {"google": 1})


def _token(vault: Vault) -> str:
    saved = vault.secret(SECRET)
    if not saved:
        raise GoogleError("Google isn't connected")
    if time.time() < saved["expires_at"]:
        return saved["access_token"]
    cid, csecret = oauth_client() or ("", "")
    r = client.post(TOKEN_URL, data={"client_id": cid, "client_secret": csecret, "grant_type": "refresh_token",
                                     "refresh_token": saved["refresh_token"]})
    if r.status_code != 200:
        raise GoogleError("Google sign-in expired; connect again in Connections")
    tok = r.json()
    saved.update(access_token=tok["access_token"], expires_at=time.time() + int(tok.get("expires_in", 3600)) - 60)
    vault.save_secret(SECRET, saved)
    return saved["access_token"]


def _call(vault: Vault, method: str, url: str, **kw) -> dict:
    r = client.request(method, url, headers={"Authorization": f"Bearer {_token(vault)}"}, **kw)
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message", r.text[:200])
        except ValueError:
            msg = r.text[:200]
        raise GoogleError(f"Google {r.status_code}: {msg}")
    return r.json() if r.content else {}


# -- Gmail -----------------------------------------------------------------------------------
def _plain(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
    for part in payload.get("parts") or []:
        text = _plain(part)
        if text:
            return text
    return ""


def _strip_quoted(text: str) -> str:
    """Drop quoted replies ('On ... wrote:' and '>' lines) so the model gets the new message, not the thread."""
    out = []
    for line in text.splitlines():
        if re.match(r"^On .+wrote:$", line.strip()) or line.startswith(">"):
            break
        out.append(line)
    return "\n".join(out).strip()


def read_inbox(vault: Vault, args: dict, limit: int = 10) -> dict:
    q = args.get("query") or ""
    listing = _call(vault, "GET", f"{GMAIL}/messages", params={"q": q or "in:inbox", "maxResults": limit})
    out = []
    for m in listing.get("messages", [])[:limit]:
        full = _call(vault, "GET", f"{GMAIL}/messages/{m['id']}", params={"format": "full"})
        headers = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
        try:
            date = parsedate_to_datetime(headers.get("date", "")).isoformat()
        except (TypeError, ValueError):
            date = ""
        body = _strip_quoted(_plain(full.get("payload", {})) or full.get("snippet", ""))
        out.append({"id": m["id"], "date": date, "from": headers.get("from", ""), "subject": headers.get("subject", ""),
                    "body": body[:1500]})
    return {"status": f"{len(out)} emails from Gmail", "messages": out}


def send_email(vault: Vault, args: dict) -> dict:
    msg = EmailMessage()
    msg["To"] = ", ".join(args["to"])
    msg["Subject"] = args["subject"]
    msg.set_content(args["body"])
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = _call(vault, "POST", f"{GMAIL}/messages/send", json={"raw": raw})
    return {"status": "sent from Gmail", "to": args["to"], "subject": args["subject"], "message_id": sent.get("id", "")}


# -- Calendar --------------------------------------------------------------------------------
TZ_NAMES = {"IST": timezone(timedelta(hours=5, minutes=30)), "UTC": timezone.utc, "GMT": timezone.utc}


def parse_when(text: str) -> datetime:
    """'2026-11-06T15:00:00+05:30', '2026-11-06 15:00 IST' or '2026-11-06 15:00' (local time)."""
    t = text.strip()
    tz = None
    m = re.search(r"\s*\b([A-Z]{2,4})$", t)
    if m and m.group(1) in TZ_NAMES:
        tz, t = TZ_NAMES[m.group(1)], t[:m.start()]
    try:
        when = datetime.fromisoformat(t.replace(" ", "T", 1) if re.match(r"\d{4}-\d\d-\d\d \d", t) else t)
    except ValueError:
        raise ValueError(f"couldn't read the time '{text}'; use YYYY-MM-DD HH:MM") from None
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz) if tz else when.astimezone()
    return when


def list_events(vault: Vault, args: dict, limit: int = 15) -> list[dict]:
    now = datetime.now(timezone.utc)
    data = _call(vault, "GET", f"{CALENDAR}/events", params={
        "timeMin": (now - timedelta(days=1)).isoformat(), "timeMax": (now + timedelta(days=60)).isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": limit, **({"q": args["query"]} if args.get("query") else {})})
    out = []
    for ev in data.get("items", []):
        attendees = [f"{a.get('displayName', '')} <{a['email']}>".strip() for a in ev.get("attendees", []) if a.get("email")]
        out.append({"google_id": ev["id"], "summary": ev.get("summary", ""), "location": ev.get("location", ""),
                    "attendees": attendees, "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date", ""),
                    "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date", "")})
    return out


def create_event(vault: Vault, args: dict) -> dict:
    start = parse_when(args["start"])
    end = start + timedelta(minutes=int(args.get("duration_minutes") or 30))
    body = {"summary": args["title"], "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
            "attendees": [{"email": a} for a in args.get("attendees") or []]}
    if args.get("location"):
        body["location"] = args["location"]
    ev = _call(vault, "POST", f"{CALENDAR}/events", params={"sendUpdates": "all"}, json=body)
    return {"status": "event created in Google Calendar", "title": args["title"], "start": start.isoformat(),
            "attendees": args.get("attendees") or [], "link": ev.get("htmlLink", "")}


def move_event(vault: Vault, google_id: str, start_text: str, end_text: str | None, old: dict) -> dict:
    start = parse_when(start_text)
    if end_text:
        end = parse_when(end_text)
    else:
        try:
            end = start + (parse_when(old["end"]) - parse_when(old["start"]))
        except (ValueError, KeyError):
            end = start + timedelta(minutes=30)
    _call(vault, "PATCH", f"{CALENDAR}/events/{google_id}", params={"sendUpdates": "all"},
          json={"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}})
    return {"status": "event moved in Google Calendar", "start": start.isoformat()}


# -- Contacts --------------------------------------------------------------------------------
def contacts(vault: Vault) -> list[dict]:
    out, token = [], None
    for _ in range(5):  # up to 1,000 contacts
        params = {"personFields": "names,emailAddresses,phoneNumbers,organizations", "pageSize": 200,
                  **({"pageToken": token} if token else {})}
        data = _call(vault, "GET", f"{PEOPLE}/people/me/connections", params=params)
        for p in data.get("connections", []):
            out.append({"name": (p.get("names") or [{}])[0].get("displayName", ""),
                        "org": (p.get("organizations") or [{}])[0].get("name", ""),
                        "emails": [e["value"] for e in p.get("emailAddresses", [])],
                        "phones": [t["value"] for t in p.get("phoneNumbers", [])]})
        token = data.get("nextPageToken")
        if not token:
            break
    return out
