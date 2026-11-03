import json

import httpx
import pytest
from fastapi.testclient import TestClient

from muse_shield.app.chat import ChatError, ChatModel
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_mask import ACCEPT, fake_spark

DEAL = "Confidential: Acme Corp will acquire Kestrel Labs for 120 crore."
ANSWERS = {
    ACCEPT: {"entities": [{"text": "Rohan", "type": "PERSON"}, {"text": "10 lakh rupees", "type": "AMOUNT", "role": "SALARY"},
                          {"text": "12-4, MVP Colony, Visakhapatnam", "type": "ADDRESS"}],
             "contexts": [{"sentences": [2], "kind": "DECISION", "subtype": "PURCHASE", "summary": "plans to buy land"}]},
    DEAL: {"entities": [{"text": "Acme Corp", "type": "ORG"}, {"text": "Kestrel Labs", "type": "ORG"},
                        {"text": "120 crore", "type": "AMOUNT", "role": "DEAL_VALUE"}],
           "contexts": [{"sentences": [1], "kind": "DEAL", "subtype": "ACQUISITION", "summary": "company acquisition"}]},
    "Is this a good offer?": {"entities": [], "contexts": []},
    "Draft a note to Rohan about my salary.": {"entities": [{"text": "Rohan", "type": "PERSON"}], "contexts": []},
}


class ScriptedModel:
    """Fake chat endpoint: replies in order, records every payload it receives."""

    def __init__(self, replies):
        self.replies, self.payloads = list(replies), []

    def transport(self):
        def handler(request):
            self.payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": self.replies.pop(0)}}],
                                             "usage": {"prompt_tokens": 900, "completion_tokens": 120}})
        return httpx.MockTransport(handler)


def make(tmp_path, replies, analyzer_calls=None):
    scripted = ScriptedModel(replies)
    model = ChatModel("https://api.meta.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=scripted.transport()))
    analyzer = fake_spark(ANSWERS)
    if analyzer_calls is not None:
        real = analyzer.analyze
        analyzer.analyze = lambda paras, labels=None: (analyzer_calls.append(paras), real(paras, labels))[1]
    return TestClient(create_app(Vault(tmp_path / "v.db", b"\x55" * 32), analyzer, model)), scripted


def raw_values_in(payload, *values):
    body = json.dumps(payload, ensure_ascii=False)
    return [v for v in values if v in body]


def test_answer_is_rehydrated_and_only_placeholders_are_sent(tmp_path):
    c, m = make(tmp_path, ["Dear <PERSON_1>, your salary of <SALARY_1> looks fine."])
    r = c.post("/chat", json={"message": ACCEPT}).json()
    assert r["error"] == "" and r["reply"] == "Dear Rohan, your salary of 10 lakh rupees looks fine."
    assert r["masked_reply"].startswith("Dear <PERSON_1>")
    assert raw_values_in(m.payloads[0], "Rohan", "10 lakh", "Visakhapatnam") == []
    assert m.payloads[0]["messages"][0]["role"] == "system" and "NEED_CONTEXT" in m.payloads[0]["messages"][0]["content"]
    assert m.payloads[0]["model"] == "muse-spark-1.3" and m.payloads[0]["reasoning_effort"] == "low"


def test_need_context_ask_allow_shape_then_answer(tmp_path):
    c, m = make(tmp_path, ["Got it.", "NEED_CONTEXT: <DEAL_1> shape need the deal terms",
                           "It depends: <DEAL_VALUE_1> for <ORG_2> is fair."])
    chat_id = c.post("/chat", json={"message": DEAL}).json()["chat_id"]
    r = c.post("/chat", json={"message": "Is this a good offer?", "chat_id": chat_id}).json()
    assert r["ask"] and r["ask"]["label"] == "<DEAL_1>" and r["ask"]["level"] == "shape" and r["reply"] == ""
    assert r["ask"]["preview"] == "Confidential: <ORG_1> will acquire <ORG_2> for <DEAL_VALUE_1>."
    assert set(r["ask"]["previews"]) == {"shape", "summary", "full"} and r["ask"]["previews"]["summary"] == "company acquisition"
    done = c.post("/reveal", json={"ask_id": r["ask"]["ask_id"], "decision": "allow"}).json()
    assert done["reply"] == "It depends: 120 crore for Kestrel Labs is fair."
    last = m.payloads[-1]["messages"][-1]["content"]
    assert "[The user allowed you to see <DEAL_1> (shape)]" in last and "Acme" not in json.dumps(m.payloads[-1])
    assert c.get(f"/chats/{chat_id}").json()["consents"][0]["decision"] == "allow"
    assert c.post("/reveal", json={"ask_id": r["ask"]["ask_id"], "decision": "allow"}).status_code == 404  # one answer per ask


def test_deny_continues_without_revealing(tmp_path):
    c, m = make(tmp_path, ["Got it.", "NEED_CONTEXT: <DEAL_1> full need details", "Without the details I can only say it depends."])
    chat_id = c.post("/chat", json={"message": DEAL}).json()["chat_id"]
    ask = c.post("/chat", json={"message": "Is this a good offer?", "chat_id": chat_id}).json()["ask"]
    assert ask["level"] == "full" and "Acme Corp" in ask["preview"]  # the card shows exactly what would go out
    r = c.post("/reveal", json={"ask_id": ask["ask_id"], "decision": "deny"}).json()
    assert r["reply"].startswith("Without the details")
    assert raw_values_in(m.payloads[-1], "Acme", "Kestrel", "120 crore") == []


def test_full_reveal_lets_values_through_only_after_consent(tmp_path):
    c, m = make(tmp_path, ["Got it.", "NEED_CONTEXT: <DEAL_1> full need exact terms", "Acme paying 120 crore is high."])
    chat_id = c.post("/chat", json={"message": DEAL}).json()["chat_id"]
    ask = c.post("/chat", json={"message": "Is this a good offer?", "chat_id": chat_id}).json()["ask"]
    r = c.post("/reveal", json={"ask_id": ask["ask_id"], "decision": "allow"}).json()
    assert r["error"] == "" and "Acme Corp will acquire" in json.dumps(m.payloads[-1])


def test_guard_refuses_unapproved_raw_values(tmp_path):
    c, m = make(tmp_path, ["ok"])
    chat_id = c.post("/chat", json={"message": ACCEPT}).json()["chat_id"]
    c.app.state.vault.add_message(chat_id, "user", "leaked: Rohan lives at 12-4, MVP Colony, Visakhapatnam")  # simulated bug
    r = c.post("/chat", json={"message": "Draft a note to Rohan about my salary.", "chat_id": chat_id}).json()
    assert "refusing to send" in r["error"] and len(m.payloads) == 1  # second call never went out


def test_mask_and_send_reuses_the_preview(tmp_path):
    calls = []
    c, _ = make(tmp_path, ["Sure, <PERSON_1>."], analyzer_calls=calls)
    preview = c.post("/mask", json={"text": "Draft a note to Rohan about my salary."}).json()
    r = c.post("/chat", json={"message": "Draft a note to Rohan about my salary.", "chat_id": preview["chat_id"],
                              "mask_id": preview["mask_id"]}).json()
    assert r["reply"] == "Sure, Rohan." and len(calls) == 1


def test_failed_analysis_is_not_sent(tmp_path):
    c, m = make(tmp_path, [])
    c.app.state.masker.analyzer = fake_spark(ANSWERS, invalid=True)
    r = c.post("/chat", json={"message": ACCEPT}).json()
    assert r["error"].startswith("Not sent") and m.payloads == []


def test_contributor_chat_model_refused():
    with pytest.raises(ChatError, match="Standard"):
        ChatModel("https://x", "muse-spark-1.3-contributor", "k")


def test_no_raw_values_on_disk_after_a_chat(tmp_path):
    c, _ = make(tmp_path, ["Hi <PERSON_1>, noted <SALARY_1>."])
    r = c.post("/chat", json={"message": ACCEPT}).json()
    raw = (tmp_path / "v.db").read_bytes()
    for value in (b"Rohan", b"10 lakh", b"MVP Colony", b"Visakhapatnam"):
        assert value not in raw, value
    # the UI can still rebuild highlights from the decrypted original + offsets
    msg = c.get(f"/chats/{r['chat_id']}").json()["messages"][0]
    spans = msg["meta"]["spans"]
    assert all("text" not in s for s in spans)
    assert {msg["text"][s["start"]:s["end"]] for s in spans} >= {"Rohan", "10 lakh rupees"}


def test_full_reveal_note_is_encrypted_at_rest(tmp_path):
    c, m = make(tmp_path, ["Got it.", "NEED_CONTEXT: <DEAL_1> full need exact terms", "High.", "Still high."])
    chat_id = c.post("/chat", json={"message": DEAL}).json()["chat_id"]
    ask = c.post("/chat", json={"message": "Is this a good offer?", "chat_id": chat_id}).json()["ask"]
    c.post("/reveal", json={"ask_id": ask["ask_id"], "decision": "allow"})
    assert b"Acme" not in (tmp_path / "v.db").read_bytes()
    c.post("/chat", json={"message": "Is this a good offer?", "chat_id": chat_id})  # later turns still carry the allowed text
    assert "Acme Corp will acquire" in json.dumps(m.payloads[-1])


def test_chat_detail_segments_restored_values(tmp_path):
    c, _ = make(tmp_path, ["Dear <PERSON_1>, about <DECISION_1>: fine."])
    r = c.post("/chat", json={"message": ACCEPT}).json()
    msgs = c.get(f"/chats/{r['chat_id']}").json()["messages"]
    seg = msgs[1]["segments"]
    assert seg[0] == {"text": "Dear "} and seg[1] == {"label": "<PERSON_1>", "kind": "entity", "text": "Rohan"}
    assert seg[3]["kind"] == "context" and seg[3]["text"].startswith("Tomorrow I'm planning")
