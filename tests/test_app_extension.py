from fastapi.testclient import TestClient

from muse_shield.app.extension import PREAMBLE, normalize_labels
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_chat import ANSWERS, DEAL
from test_app_mask import ACCEPT, fake_spark


def make(tmp_path):
    return TestClient(create_app(Vault(tmp_path / "v.db", b"\x66" * 32), fake_spark(ANSWERS)))


def test_first_message_carries_the_preamble_and_no_raw_values(tmp_path):
    c = make(tmp_path)
    r = c.post("/ext/mask", json={"text": ACCEPT}).json()
    assert r["analysis_ok"] and r["first"]
    assert r["outbound"] == f"{PREAMBLE}\n\nMy name is <PERSON_1> and I earn <SALARY_1>. <DECISION_1>"
    assert not any(v in r["outbound"] for v in ("Rohan", "10 lakh", "Visakhapatnam"))
    again = c.post("/ext/mask", json={"text": "Is this a good offer?", "chat_id": r["chat_id"]}).json()
    assert not again["first"] and again["outbound"] == "Is this a good offer?"


def test_bind_new_chat_once_meta_assigns_an_id_then_history_comes_back(tmp_path):
    c = make(tmp_path)
    assert c.post("/ext/bind", json={"conversation_id": "abc"}).json()["chat_id"] is None
    r = c.post("/ext/mask", json={"text": ACCEPT}).json()
    b = c.post("/ext/bind", json={"conversation_id": "abc", "chat_id": r["chat_id"]}).json()
    assert b["chat_id"] == r["chat_id"]
    c.post("/ext/reply", json={"chat_id": r["chat_id"], "text": "Hi <PERSON_1>!", "message_id": "m1"})
    h = c.post("/ext/bind", json={"conversation_id": "abc"}).json()["messages"]
    assert [m["role"] for m in h] == ["user", "assistant"]
    assert h[0]["text"] == ACCEPT and h[0]["masked"].startswith(PREAMBLE[:20])
    assert "".join(s["text"] for s in h[1]["segments"]) == "Hi Rohan!"


def test_reply_restores_bracket_variants_and_is_stored_once(tmp_path):
    c = make(tmp_path)
    cid = c.post("/ext/mask", json={"text": ACCEPT}).json()["chat_id"]
    text = "Dear [PERSON_1], about SALARY_1 and <ADDRESS_1>; FOO_9 stays."
    for _ in range(2):
        r = c.post("/ext/reply", json={"chat_id": cid, "text": text, "message_id": "m1"}).json()
    assert "".join(s["text"] for s in r["segments"]) == "Dear Rohan, about 10 lakh rupees and 12-4, MVP Colony, Visakhapatnam; FOO_9 stays."
    assert sum(m["role"] == "assistant" for m in c.app.state.vault.messages(cid)) == 1


def test_need_context_becomes_an_ask_and_consent_builds_the_note(tmp_path):
    c = make(tmp_path)
    cid = c.post("/ext/mask", json={"text": DEAL}).json()["chat_id"]
    r = c.post("/ext/reply", json={"chat_id": cid, "text": "NEED_CONTEXT: <DEAL_1> summary to judge the offer"}).json()
    ask = r["ask"]
    assert ask["label"] == "<DEAL_1>" and ask["level"] == "summary" and set(ask["previews"]) == {"shape", "summary", "full"}
    assert "Acme" not in ask["previews"]["shape"]
    assert not any(m["role"] == "assistant" for m in c.app.state.vault.messages(cid))  # the request line isn't an answer
    note = c.post("/ext/consent", json={"chat_id": cid, "label": "<DEAL_1>", "level": "summary", "decision": "allow"}).json()
    assert note["outbound"] == "[I allowed you to see <DEAL_1> (summary)]: company acquisition"
    deny = c.post("/ext/consent", json={"chat_id": cid, "label": "<DEAL_1>", "level": "full", "decision": "deny"}).json()
    assert "declined" in deny["outbound"] and "Acme" not in deny["outbound"]


def test_full_reveal_is_allowed_only_after_consent_and_not_kept_in_clear(tmp_path):
    c = make(tmp_path)
    cid = c.post("/ext/mask", json={"text": DEAL}).json()["chat_id"]
    note = c.post("/ext/consent", json={"chat_id": cid, "label": "<DEAL_1>", "level": "full", "decision": "allow"}).json()["outbound"]
    assert "Acme Corp will acquire Kestrel Labs" in note
    raw = (tmp_path / "v.db").read_bytes()
    assert b"Kestrel" not in raw and b"Acme" not in raw


def test_mask_unavailable_without_analysis(tmp_path):
    c = TestClient(create_app(Vault(tmp_path / "v.db", b"\x66" * 32)))
    assert c.post("/ext/mask", json={"text": ACCEPT}).status_code == 503


def test_normalize_leaves_unknown_labels():
    m = {"<PERSON_1>": "Rohan"}
    assert normalize_labels("[PERSON_1] PERSON_1 <PERSON_1> PERSON_2 X_PERSON_1", m) == "<PERSON_1> <PERSON_1> <PERSON_1> PERSON_2 X_PERSON_1"
