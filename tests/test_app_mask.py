import json

import httpx
import pytest
from fastapi.testclient import TestClient

from muse_shield.backends import GlimmerBackend
from muse_shield.app.engine import Masker, rehydrate
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault

ACCEPT = "My name is Rohan and I earn 10 lakh rupees. Tomorrow I'm planning to buy a land at 12-4, MVP Colony, Visakhapatnam."

ANSWERS = {  # paragraph -> what a correct analyzer returns
    ACCEPT: {"entities": [{"text": "Rohan", "type": "PERSON"}, {"text": "10 lakh rupees", "type": "AMOUNT", "role": "SALARY"},
                          {"text": "12-4, MVP Colony, Visakhapatnam", "type": "ADDRESS"}],
             "contexts": [{"sentences": [2], "kind": "DECISION", "subtype": "PURCHASE", "summary": "plans to buy land"}]},
    "Ask Rohan to call me.": {"entities": [{"text": "Rohan", "type": "PERSON"}], "contexts": []},
    "Priya Shah met Rohan.": {"entities": [{"text": "Priya Shah", "type": "PERSON"}, {"text": "Rohan", "type": "PERSON"},
                                           {"text": "Rohan Kumar", "type": "PERSON"}], "contexts": []},
}


def fake_spark(answers=ANSWERS, invalid=False):
    def handler(request):
        msgs = json.loads(request.content)["messages"]
        para = [m["content"] for m in msgs if m["content"].startswith("Known contexts")][-1].split("\n", 1)[1]
        para = " ".join(part.split("] ", 1)[1] for part in para.split(" [") if "] " in part)
        content = "not json" if invalid else json.dumps(answers[para])
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 600, "completion_tokens": 80}})
    return GlimmerBackend("https://spark.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Vault(tmp_path / "v.db", b"\x33" * 32), fake_spark()))


def test_acceptance_mask_and_exact_unmask(client):
    r = client.post("/mask", json={"text": ACCEPT}).json()
    assert r["analysis_ok"]
    assert r["masked_text"] == "My name is <PERSON_1> and I earn <SALARY_1>. <DECISION_1>"
    labels = {s["placeholder"] for s in r["spans"]}
    assert labels == {"<PERSON_1>", "<SALARY_1>", "<ADDRESS_1>", "<DECISION_1>"}
    assert r["contexts"][0]["summary"] == "plans to buy land" and r["cost_usd"] > 0
    back = client.post("/unmask", json={"text": r["masked_text"], "chat_id": r["chat_id"]}).json()
    assert back["text"] == ACCEPT and back["unknown"] == []


def test_context_shape_hides_inner_values(client):
    r = client.post("/mask", json={"text": ACCEPT}).json()
    shape = client.app.state.vault.resolve(r["chat_id"], "<DECISION_1>", "shape")
    assert shape == "Tomorrow I'm planning to buy a land at <ADDRESS_1>."
    assert "Visakhapatnam" not in shape


def test_same_person_same_placeholder_across_messages(client):
    a = client.post("/mask", json={"text": ACCEPT}).json()
    b = client.post("/mask", json={"text": "Ask Rohan to call me.", "chat_id": a["chat_id"]}).json()
    assert b["masked_text"] == "Ask <PERSON_1> to call me."


def test_hallucinated_and_overlapping_spans(client):
    r = client.post("/mask", json={"text": "Priya Shah met Rohan."}).json()
    assert r["masked_text"] == "<PERSON_1> met <PERSON_2>."  # 'Rohan Kumar' isn't in the text, so it's dropped


def test_failed_analysis_blocks(tmp_path):
    c = TestClient(create_app(Vault(tmp_path / "v.db", b"\x44" * 32), fake_spark(invalid=True)))
    r = c.post("/mask", json={"text": ACCEPT}).json()
    assert not r["analysis_ok"] and "invalid" in r["error"] and r["masked_text"] == ACCEPT


def test_analysis_off_by_default_and_contributor_refused(tmp_path, monkeypatch):
    from muse_shield.app.server import analyzer_from_env

    monkeypatch.setenv("MODEL_API_KEY", "k")
    assert analyzer_from_env()[0] is None and "MUSE_SHIELD_DEV_RAW_ANALYSIS" in analyzer_from_env()[1]
    monkeypatch.setenv("MUSE_SHIELD_DEV_RAW_ANALYSIS", "1")
    monkeypatch.setenv("MUSE_SHIELD_MODEL", "muse-spark-1.3-contributor")
    assert analyzer_from_env()[0] is None and "Standard" in analyzer_from_env()[1]
    monkeypatch.setenv("MUSE_SHIELD_MODEL", "muse-spark-1.3")
    assert analyzer_from_env()[0].model == "muse-spark-1.3"


def test_vault_graph_and_reveal_endpoints(client):
    r = client.post("/mask", json={"text": ACCEPT}).json()
    cid = r["chat_id"]
    v = client.get(f"/chats/{cid}/vault").json()
    assert {e["label"] for e in v["entities"]} == {"<PERSON_1>", "<SALARY_1>", "<ADDRESS_1>"} and v["contexts"][0]["kind"] == "DECISION"
    g = client.get(f"/chats/{cid}/graph").json()
    assert {"source": "<ADDRESS_1>", "target": "<DECISION_1>", "rel": "mentioned_in", "weight": 1} in g["edges"]
    assert client.post("/vault/reveal", json={"chat_id": cid, "label": "<SALARY_1>"}).json()["value"] == "10 lakh rupees"
    assert client.get("/chats/nope/vault").status_code == 404


def test_rehydrate_reports_unknown_labels():
    assert rehydrate("Hi <PERSON_1> and <PERSON_9>", {"<PERSON_1>": "Rohan"}) == ("Hi Rohan and <PERSON_9>", ["<PERSON_9>"])
