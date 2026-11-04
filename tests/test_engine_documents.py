"""Masker options used by documents. Chat behaviour (the defaults) is covered by test_app_mask.py."""

from doc_fakes import fake_values

from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault


def _masker(tmp_path, **kw):
    vault = Vault(tmp_path / "v.db", b"\x44" * 32)
    return vault, Masker(vault, fake_values(**kw))


def test_propagate_masks_every_occurrence(tmp_path):
    vault, m = _masker(tmp_path, values={"Arjun Malhotra": "PERSON"})
    text = "Offer for Arjun Malhotra.\n\nThe salary is fixed.\n\nSigned: arjun  malhotra"
    plain = m.mask(text, vault.create_chat())
    assert "arjun  malhotra" in plain.masked_text  # the fake only flags the exact casing
    doc = m.mask(text, vault.create_chat(), propagate=True)
    assert doc.masked_text == "Offer for <PERSON_1>.\n\nThe salary is fixed.\n\nSigned: <PERSON_1>"


def test_replacements_match_masked_text(tmp_path):
    vault, m = _masker(tmp_path, values={"Priya": "PERSON", "₹40 lakh": "AMOUNT"},
                       contexts={"acquire": "DEAL"}, roles={"₹40 lakh": "PRICE"})
    text = "Priya called.\n\nWe will acquire Kestrel for ₹40 lakh. It closes soon."
    r = m.mask(text, vault.create_chat())
    rebuilt, cur = [], 0
    for s, e, label in r.replacements():
        rebuilt += [text[cur:s], label]
        cur = e
    assert "".join(rebuilt + [text[cur:]]) == r.masked_text == "<PERSON_1> called.\n\n<DEAL_1> It closes soon."


def test_already_sent_values_are_returned(tmp_path):
    vault, m = _masker(tmp_path, values={"Pr0d!Acme#2026": "SECRET"})
    chat = vault.create_chat()
    vault.add_message(chat, "user", "the password is Pr0d!Acme#2026", "the password is Pr0d!Acme#2026", {})
    r = m.mask("Rotate Pr0d!Acme#2026 today.", chat)
    assert r.masked_text == "Rotate Pr0d!Acme#2026 today."
    assert [a["text"] for a in r.already_sent] == ["Pr0d!Acme#2026"]


def test_progress_and_no_title(tmp_path):
    vault, m = _masker(tmp_path, values={"Rohan": "PERSON"})
    chat = vault.create_chat()
    seen = []
    m.mask("Rohan wrote.\n\nRohan signed.\n\nDone.", chat, on_progress=lambda d, t: seen.append((d, t)), title=False)
    assert seen[0] == (0, 3) and seen[-1] == (3, 3)
    assert next(c for c in vault.chats() if c["chat_id"] == chat)["title"] in ("", "New chat", None)
