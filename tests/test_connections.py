"""Connections: Google and Telegram sign-in from the app, their tools on real accounts (mocked here), and the folder choice."""

import base64
import json
import urllib.parse
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from telethon.errors import SessionPasswordNeededError

from muse_shield.agent.executor import Executor
from muse_shield.app.engine import Masker
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from muse_shield.connectors import google, telegram
from test_connectors import lookup_spark


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "v.db", b"\x81" * 32)


@pytest.fixture
def app(vault):
    return TestClient(create_app(vault, lookup_spark()))


# -- Google --------------------------------------------------------------------------------------
class FakeGoogle:
    """Google's token, userinfo, Gmail, Calendar and People endpoints, recording what was sent."""

    def __init__(self):
        self.sent, self.created, self.patched, self.revoked = [], [], [], []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url, j = str(req.url), lambda d: httpx.Response(200, json=d)
        if url.startswith(google.TOKEN_URL):
            form = urllib.parse.parse_qs(req.content.decode())
            assert form["grant_type"][0] in ("authorization_code", "refresh_token")
            if form["grant_type"][0] == "authorization_code":
                assert form["code_verifier"][0]  # PKCE
            return j({"access_token": "at-1", "refresh_token": "rt-secret-1", "expires_in": 3600, "scope": " ".join(google.SCOPES)})
        if url.startswith(google.USERINFO_URL):
            return j({"email": "demo.muse@gmail.com"})
        if url.startswith(google.REVOKE_URL):
            self.revoked.append(req.content)
            return j({})
        if "/messages/send" in url:
            self.sent.append(json.loads(req.content))
            return j({"id": "sent-1"})
        if "/messages/" in url:
            body = base64.urlsafe_b64encode(b"Invoice INV-2231 for \xe2\x82\xb92,40,000 is due.\n\nOn Mon, Ravi wrote:\n> old").decode()
            return j({"snippet": "...", "payload": {"mimeType": "text/plain", "body": {"data": body}, "headers": [
                {"name": "From", "value": "Rahul Mehta <rahul.mehta@brightpath.in>"}, {"name": "Subject", "value": "Invoice"},
                {"name": "Date", "value": "Mon, 03 Nov 2026 09:12:00 +0530"}]}})
        if "/messages" in url:
            return j({"messages": [{"id": "m1"}]})
        if "/calendars/primary/events/" in url and req.method == "PATCH":
            self.patched.append(json.loads(req.content))
            return j({})
        if "/calendars/primary/events" in url and req.method == "POST":
            self.created.append(json.loads(req.content))
            return j({"htmlLink": "https://calendar.google.com/e/1"})
        if "/calendars/primary/events" in url:
            return j({"items": [{"id": "g-ev-1", "summary": "Project Banyan budget review", "location": "MG Road",
                                 "attendees": [{"email": "ananya@northwind.in", "displayName": "Ananya Iyer"}],
                                 "start": {"dateTime": "2026-11-05T15:00:00+05:30"}, "end": {"dateTime": "2026-11-05T16:00:00+05:30"}}]})
        if "people/me/connections" in url:
            return j({"connections": [{"names": [{"displayName": "Rahul Mehta"}], "emailAddresses": [{"value": "rahul.mehta@brightpath.in"}],
                                       "organizations": [{"name": "Brightpath Studio"}]}]})
        raise AssertionError(f"unexpected Google call {req.method} {url}")


@pytest.fixture
def fake_google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(google, "client", httpx.Client(transport=httpx.MockTransport(fake)))
    monkeypatch.setenv("MUSE_SHIELD_GOOGLE_CLIENT_ID", "app-client.apps.googleusercontent.com")
    monkeypatch.setenv("MUSE_SHIELD_GOOGLE_CLIENT_SECRET", "not-confidential")
    return fake


def sign_in(app) -> None:
    url = app.post("/connections/google/start").json()["url"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert q["redirect_uri"][0].endswith("/connections/google/callback")
    page = app.get("/connections/google/callback", params={"code": "auth-code", "state": q["state"][0]})
    assert "Google connected" in page.text


def test_google_not_offered_without_the_apps_key(app, monkeypatch):
    for v in ("MUSE_SHIELD_GOOGLE_CLIENT_ID", "MUSE_SHIELD_GOOGLE_CLIENT_FILE"):
        monkeypatch.delenv(v, raising=False)
    assert app.get("/connections").json()["google"] == {"configured": False, "connected": False, "account": None,
                                                         "services": ["Gmail", "Calendar", "Contacts"]}
    assert app.post("/connections/google/start").status_code == 409


def test_google_sign_in_keeps_the_token_encrypted_and_a_link_works_once(app, vault, fake_google, tmp_path):
    sign_in(app)
    status = app.get("/connections").json()["google"]
    assert status["connected"] and status["account"] == "demo.muse@gmail.com"
    assert b"rt-secret-1" not in (tmp_path / "v.db").read_bytes()
    url = app.post("/connections/google/start").json()["url"]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    app.get("/connections/google/callback", params={"code": "c", "state": state})
    assert "expired or was already used" in app.get("/connections/google/callback", params={"code": "c", "state": state}).text
    assert app.delete("/connections/google").json()["connected"] is False and fake_google.revoked


def test_gmail_reads_come_back_masked_and_sends_go_through_gmail(app, vault, fake_google):
    sign_in(app)
    ex = Executor(vault, masker=Masker(vault, lookup_spark()))
    chat = vault.create_chat()
    read = ex.propose(chat, "read_inbox", {})
    mail = read.result["messages"][0]
    assert "Rahul" not in json.dumps(read.result) and "<PERSON_1>" in mail["from"] and "old" not in mail["body"]  # quote dropped
    assert read.result["status"] == "1 emails from Gmail"
    ex.propose(chat, "search_contacts", {"query": "Rahul"})  # your Google contacts vouch for the address
    rahul = next(k for k, v in vault.mapping(chat).items() if v == "Rahul Mehta")
    send = ex.propose(chat, "send_email", {"to": [rahul], "subject": "Paid", "body": "Paid today."})
    assert send.status == "pending" and fake_google.sent == []  # nothing leaves before you confirm
    ex.confirm(send.action_id)
    raw = base64.urlsafe_b64decode(fake_google.sent[0]["raw"]).decode()
    assert "To: rahul.mehta@brightpath.in" in raw and send.result["status"] == "sent from Gmail"


def test_google_calendar_create_and_move(app, vault, fake_google):
    sign_in(app)
    ex = Executor(vault, masker=Masker(vault, lookup_spark()))
    chat = vault.create_chat()
    listed = ex.propose(chat, "list_events", {})
    ev = listed.result["events"][0]
    assert "Ananya" not in ev["event"] and ev["start"] == "2026-11-05T15:00:00+05:30" and "g-ev-1" not in json.dumps(listed.result)
    move = ex.propose(chat, "reschedule_event", {"event_id": ev["id"], "start": "2026-11-06 15:00 IST"})
    ex.confirm(move.action_id)
    assert fake_google.patched[0]["start"]["dateTime"] == "2026-11-06T15:00:00+05:30"
    assert fake_google.patched[0]["end"]["dateTime"] == "2026-11-06T16:00:00+05:30"  # keeps the hour's length


# -- Telegram ------------------------------------------------------------------------------------
class FakeTelegram:
    """Just enough of Telethon's TelegramClient: sign-in with a two-step password, dialogs, messages, send."""
    state = {"sent": [], "logged_out": False}

    def __init__(self, session=""):
        self.session = SimpleNamespace(save=lambda: "session-" + str(len(self.state["sent"])))
        self._session = session

    async def connect(self): ...
    async def disconnect(self): ...

    async def send_code_request(self, phone):
        return SimpleNamespace(phone_code_hash="hash-1")

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        if password is None:
            raise SessionPasswordNeededError(None)
        assert password == "two-step"

    async def get_me(self):
        return SimpleNamespace(first_name="Demo", last_name="Muse", username=None)

    async def get_dialogs(self, limit=15):
        msg = SimpleNamespace(message="Can you send me Priya's address?")
        return [SimpleNamespace(id=111, name="Ananya Iyer", is_group=False, is_channel=False, unread_count=2, message=msg),
                SimpleNamespace(id=222, name="Family", is_group=True, is_channel=False, unread_count=0, message=msg)]

    async def get_messages(self, chat, limit=20):
        async def sender():
            return SimpleNamespace(first_name="Ananya", last_name="Iyer")
        return [SimpleNamespace(id=1, message="Meet at 5? Priya Shah will join.", out=False, date=None, get_sender=sender)]

    async def send_message(self, chat, text):
        self.state["sent"].append((chat, text))
        return SimpleNamespace(id=99)

    async def log_out(self):
        self.state["logged_out"] = True


@pytest.fixture
def fake_tg(monkeypatch):
    FakeTelegram.state = {"sent": [], "logged_out": False}
    monkeypatch.setattr(telegram, "make_client", FakeTelegram)
    monkeypatch.setenv("MUSE_SHIELD_TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("MUSE_SHIELD_TELEGRAM_API_HASH", "app-hash")
    return FakeTelegram


def test_telegram_sign_in_with_a_two_step_password(app, fake_tg):
    assert app.post("/connections/telegram/start", json={"phone": "+91 98765 43210"}).json()["step"] == "code"
    assert app.post("/connections/telegram/verify", json={"code": "12345"}).json()["step"] == "password"
    done = app.post("/connections/telegram/verify", json={"password": "two-step"}).json()
    assert done["connected"] and done["account"] == "Demo Muse"
    assert app.delete("/connections/telegram").json()["connected"] is False and fake_tg.state["logged_out"]


def test_telegram_reads_masked_and_sends_only_to_your_chats(app, vault, fake_tg):
    app.post("/connections/telegram/start", json={"phone": "+91 98765 43210"})
    app.post("/connections/telegram/verify", json={"code": "1"})
    app.post("/connections/telegram/verify", json={"password": "two-step"})
    ex = Executor(vault, masker=Masker(vault, lookup_spark()))
    chat = vault.create_chat()
    chats = ex.propose(chat, "read_telegram", {})
    assert "Ananya" not in json.dumps(chats.result) and [c["kind"] for c in chats.result["chats"]] == ["private", "group"]
    ananya = chats.result["chats"][0]["id"]
    msgs = ex.propose(chat, "read_telegram", {"chat_id": ananya})
    assert "Priya" not in json.dumps(msgs.result) and msgs.result["messages"][0]["message"].startswith("<PERSON_")
    assert ex.propose(chat, "send_telegram", {"chat_id": "@attacker", "text": "hi"}).status == "refused"
    send = ex.propose(chat, "send_telegram", {"chat_id": ananya, "text": "See you at 5"})
    assert send.status == "pending" and send.recipients[0]["person"] == "Ananya Iyer" and fake_tg.state["sent"] == []
    ex.confirm(send.action_id)
    assert fake_tg.state["sent"] == [(111, "See you at 5")]


# -- documents folder ----------------------------------------------------------------------------
def test_choose_a_folder_and_go_back_to_samples(app, tmp_path, monkeypatch):
    monkeypatch.delenv("MUSE_SHIELD_FILES", raising=False)
    mine = tmp_path / "mine"
    mine.mkdir()
    assert app.post("/connections/folder", json={"path": str(tmp_path / "nope")}).status_code == 400
    assert app.post("/connections/folder", json={"path": str(mine)}).json()["path"] == str(mine.resolve())
    assert app.get("/connections").json()["folder"]["path"] == str(mine.resolve())
    assert app.delete("/connections/folder").json() == {"connected": False}
