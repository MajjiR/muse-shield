from fastapi.testclient import TestClient

from privacy_engine.cli import DEMO_PROMPTS
from privacy_engine.server import create_app


def test_audit_proves_no_raw_values_left(engine):
    for p in DEMO_PROMPTS:
        assert not engine.ask(p).error
    a = engine.audit()
    assert a["clean"] and a["requests_scanned"] == len(DEMO_PROMPTS) and a["secrets_checked"] >= 8
    # "Meta" was masked inside the acquisition memo but is fine in a public question.
    assert any("ORG" in t for hit in a["public_in_context"] for t in hit["tokens"])


def test_audit_detects_a_planted_leak(engine):
    engine.ask("Email John Smith")
    engine.inspector.records[-1].request_body += " John Smith"  # simulate a bug that leaked
    a = engine.audit()
    assert not a["clean"] and a["leaks"][0]["tokens"] == ["PERSON_1"]


def test_raw_send_is_refused_before_egress(engine):
    c = TestClient(create_app(engine))
    r = c.post("/api/inspector/attack", json={"text": "Sarah Chen SSN 123-45-6789"}).json()
    assert r == {"sent": False, "refused": r["refused"], "requests_added": 0}
    assert "PERSON_1" in r["refused"]
    assert c.get("/api/inspector/audit").json()["requests_scanned"] == 0
