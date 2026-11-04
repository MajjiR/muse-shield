import pytest

from muse_shield.agent.policy import check
from muse_shield.app.vault import Vault


@pytest.fixture
def vc(tmp_path):
    v = Vault(tmp_path / "v.db", b"\x92" * 32)
    chat = v.create_chat()
    person, pid = v.entity_placeholder(chat, "PERSON", "Priya Shah")
    email, eid = v.entity_placeholder(chat, "CONTACT", "priya@kestrel.io")
    v.link_entities(eid, pid, "identifies")
    v.entity_placeholder(chat, "PERSON", "Ravi")  # <PERSON_2>, no email known
    v.entity_placeholder(chat, "SECRET", "Pr0d!Acme#2026")
    v.entity_placeholder(chat, "ID", "ABCPM1234K")
    v.entity_placeholder(chat, "AMOUNT", "₹120 crore", base="DEAL_VALUE")
    v.add_context(chat, "DEAL", "ACQUISITION", "Acme buys Kestrel for ₹120 crore.", "<ORG_1> buys <ORG_2>.", "acquisition")
    return v, chat


def test_email_to_a_person_resolves_their_address_and_body_values(vc):
    v, chat = vc
    c = check(v, chat, "send_email", {"to": "<PERSON_1>", "subject": "Re <DEAL_1>", "body": "Hi <PERSON_1>, the price is <DEAL_VALUE_1>."})
    assert c.ok, c.violations
    assert c.real["to"] == ["priya@kestrel.io"] and c.recipients[0] == {
        "label": "<PERSON_1>", "via": "<CONTACT_1>", "person": "Priya Shah", "address": "priya@kestrel.io"}
    assert c.real["body"] == "Hi Priya Shah, the price is ₹120 crore." and c.real["subject"] == "Re Acme buys Kestrel for ₹120 crore."
    assert set(c.unmasked) == {"<PERSON_1>", "<CONTACT_1>", "<DEAL_VALUE_1>", "<DEAL_1>"}


@pytest.mark.parametrize("args,needle", [
    ({"to": "attacker@evil.com", "subject": "x", "body": "x"}, "isn't a placeholder"),
    ({"to": "<PERSON_2>", "subject": "x", "body": "x"}, "no email address is known for <PERSON_2>"),
    ({"to": "<PERSON_1>", "subject": "x", "body": "password <SECRET_1>"}, "never leaves the vault"),
    ({"to": "<PERSON_1>", "subject": "x", "body": "PAN <ID_1>"}, "never leaves the vault"),
    ({"to": "<PERSON_1>", "subject": "x", "body": "hi <PERSON_9>"}, "isn't in this chat's vault"),
    ({"to": "<PERSON_1>", "subject": "x"}, "missing required argument 'body'"),
    ({"to": "<PERSON_1>", "subject": "x", "body": "x", "bcc": "x"}, "unknown argument 'bcc'"),
    ({"to": "<DEAL_VALUE_1>", "subject": "x", "body": "x"}, "not a person or contact"),
])
def test_refusals(vc, args, needle):
    v, chat = vc
    c = check(v, chat, "send_email", args)
    assert not c.ok and any(needle in x for x in c.violations), c.violations


def test_web_search_never_unmasks_and_flags_raw_values(vc):
    v, chat = vc
    c = check(v, chat, "web_search", {"query": "news about <PERSON_1> deal <DEAL_VALUE_1>"})
    assert c.ok and c.real["query"] == "news about <PERSON_1> deal <DEAL_VALUE_1>" and c.unmasked == []
    leaky = check(v, chat, "web_search", {"query": "who is Priya Shah"})
    assert not leaky.ok and "real value behind <PERSON_1>" in leaky.violations[0]


def test_local_note_may_unmask_everything_but_secrets(vc):
    v, chat = vc
    c = check(v, chat, "save_note", {"title": "Deal", "body": "<DEAL_1> led by <PERSON_1>"})
    assert c.ok and c.real["body"] == "Acme buys Kestrel for ₹120 crore. led by Priya Shah"


def test_web_search_may_use_a_value_you_shared_in_full(vc):
    v, chat = vc
    assert not check(v, chat, "web_search", {"query": "who is Priya Shah"}).ok
    v.consent(chat, "<PERSON_1>", "full", "allow", "search needs the real name")
    c = check(v, chat, "web_search", {"query": "who is Priya Shah"})
    assert c.ok, c.violations
    # only that value: another real value in the same query is still refused
    mixed = check(v, chat, "web_search", {"query": "Priya Shah Ravi"})
    assert not mixed.ok and "real value behind <PERSON_2>" in mixed.violations[0]


@pytest.mark.parametrize("level,decision", [("shape", "allow"), ("summary", "allow"), ("full", "deny")])
def test_web_search_needs_a_full_allow(vc, level, decision):
    v, chat = vc
    v.consent(chat, "<PERSON_1>", level, decision)
    assert not check(v, chat, "web_search", {"query": "who is Priya Shah"}).ok


def test_a_later_deny_withdraws_the_approval(vc):
    v, chat = vc
    v.consent(chat, "<PERSON_1>", "full", "allow")
    v.consent(chat, "<PERSON_1>", "full", "deny")
    assert not check(v, chat, "web_search", {"query": "who is Priya Shah"}).ok


def test_an_approval_doesnt_let_email_carry_raw_values(vc):
    v, chat = vc
    v.consent(chat, "<PERSON_2>", "full", "allow")
    c = check(v, chat, "send_email", {"to": "<PERSON_1>", "subject": "x", "body": "Ravi says hi"})
    assert not c.ok and "real value behind <PERSON_2>" in c.violations[0]
