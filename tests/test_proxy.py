import json

from fastapi.testclient import TestClient

from privacy_engine.entities import EntityType as T
from privacy_engine.policy import Action
from privacy_engine.server import create_app


def client(engine):
    return TestClient(create_app(engine))


def test_openai_compatible_roundtrip(engine):
    c = client(engine)
    r = c.post("/v1/chat/completions", headers={"Authorization": "Bearer sk-client-key"}, json={
        "model": "anything",
        "messages": [
            {"role": "system", "content": "You help Sarah Chen with deals."},
            {"role": "user", "content": "Draft an email to Sarah Chen about the $1.2B offer."},
        ],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert "Sarah Chen" in body["choices"][0]["message"]["content"]
    assert "PERSON_1" in body["privacy"]["tokens"]

    sent = engine.inspector.records[-1]
    assert "Sarah Chen" not in sent.request_body and "$1.2B" not in sent.request_body
    assert "sk-client-key" not in sent.request_body  # client's key never forwarded
    assert sent.clean


def test_history_stays_consistent_across_stateless_calls(engine):
    c = client(engine)
    history = [{"role": "user", "content": "Summarize my call with John Smith at Acme Corp."}]
    first = c.post("/v1/chat/completions", json={"messages": history}).json()
    history += [first["choices"][0]["message"], {"role": "user", "content": "Now draft a note to John Smith."}]
    c.post("/v1/chat/completions", json={"messages": history})
    sent = json.loads(engine.inspector.records[-1].request_body)["messages"]
    user_turns = [m["content"] for m in sent if m["role"] == "user"]
    assert "PERSON_1" in user_turns[0] and user_turns[-1] == "Now draft a note to PERSON_1."
    assert "John" not in engine.inspector.records[-1].request_body


def test_streaming_sends_restored_answer(engine):
    r = client(engine).post("/v1/chat/completions", json={"stream": True, "messages": [{"role": "user", "content": "Email Priya Raman"}]})
    lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    assert "Priya Raman" in json.loads(lines[0][6:])["choices"][0]["delta"]["content"]


def test_blocked_and_images_never_sent(engine):
    engine.policy.type_actions[T.SSN] = Action.BLOCK
    c = client(engine)
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "SSN 123-45-6789"}]})
    assert r.status_code == 400 and r.json()["error"]["type"] == "privacy_blocked"
    img = [{"type": "text", "text": "what is this"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    r = c.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": img}]})
    assert r.status_code == 400 and r.json()["error"]["type"] == "unsupported_content"
    assert len(engine.inspector.records) == 0


def test_models_endpoint(engine):
    assert client(engine).get("/v1/models").json()["data"][0]["id"] == engine.cloud.model
