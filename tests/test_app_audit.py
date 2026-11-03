import json

import httpx
from fastapi.testclient import TestClient

from muse_shield.app.chat import ChatModel
from muse_shield.app.inspector import Inspector
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_chat import ANSWERS, ScriptedModel
from test_app_mask import ACCEPT, fake_spark


def make(tmp_path, replies):
    ins = Inspector()
    scripted = ScriptedModel(replies)
    model = ChatModel("https://api.meta.test/v1", "muse-spark-1.3", "k", client=ins.client("chat", transport=scripted.transport()))
    return TestClient(create_app(Vault(tmp_path / "v.db", b"\x66" * 32), fake_spark(ANSWERS), model, inspector=ins))


def test_inspector_shows_masked_chat_requests_and_audit_is_clean(tmp_path):
    c = make(tmp_path, ["Hi <PERSON_1>."])
    chat_id = c.post("/chat", json={"message": ACCEPT}).json()["chat_id"]
    ins = c.get("/inspector").json()
    (req,) = [r for r in ins["requests"] if r["purpose"] == "chat"]
    assert req["chat_id"] == chat_id and "<PERSON_1>" in req["request_body"] and "Rohan" not in req["request_body"]
    audit = c.get("/inspector/audit").json()
    assert audit["clean"] and audit["chat_requests_scanned"] == 1 and audit["checks"] >= 4


def test_audit_catches_a_raw_value_in_a_chat_request(tmp_path):
    c = make(tmp_path, ["ok"])
    chat_id = c.post("/chat", json={"message": ACCEPT}).json()["chat_id"]
    rec = dict(c.app.state.inspector.records[-1])
    rec["id"], rec["request_body"] = "planted", json.dumps({"messages": [{"role": "user", "content": "Rohan earns 10 lakh rupees"}]})
    c.app.state.inspector.records.append(rec)
    audit = c.get("/inspector/audit").json()
    assert not audit["clean"] and audit["leaks"][0]["chat_id"] == chat_id
    assert set(audit["leaks"][0]["labels"]) >= {"<PERSON_1>", "<SALARY_1>"}


def test_metrics_counts_and_costs(tmp_path):
    c = make(tmp_path, ["Hi <PERSON_1>."])
    chat_id = c.post("/chat", json={"message": ACCEPT}).json()["chat_id"]
    m = c.get("/metrics").json()
    assert m["masked_by_type"]["PERSON"] == 1 and m["masked_by_type"]["CONTEXT_DECISION"] == 1
    assert m["cost_by_chat"][chat_id] > 0 and m["cost_total"] > 0 and m["inspector"]["chat_requests"] == 1
