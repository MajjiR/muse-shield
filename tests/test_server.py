from fastapi.testclient import TestClient

from privacy_engine.server import create_app


def test_dashboard_api_flow(engine):
    c = TestClient(create_app(engine))
    assert c.get("/").status_code == 200
    s = c.get("/api/status").json()
    assert s["cloud_mock"] and s["inspector"]["leaks"] == 0

    r = c.post("/api/ask", json={"text": "Email John Smith about the $1.2B deal"}).json()
    assert "PERSON_1" in r["protected"]["masked"]["masked"]
    assert "John Smith" in r["answer"]

    vault = c.get("/api/vault").json()
    assert {v["token"] for v in vault} >= {"PERSON_1", "MAJOR_TRANSACTION_VALUE"}
    assert c.post("/api/vault/reveal", json={"token": "PERSON_1"}).json()["value"] == "John Smith"
    assert c.post("/api/vault/reveal", json={"token": "PERSON_99"}).status_code == 404

    insp = c.get("/api/inspector").json()
    assert insp["summary"]["requests"] == 1 and insp["records"][0]["clean"]


def test_policy_update_applies(engine, tmp_path):
    c = TestClient(create_app(engine))
    p = c.get("/api/policy").json()
    p["type_actions"]["EMAIL"] = "block"
    assert c.put("/api/policy", json=p).status_code == 200
    r = c.post("/api/ask", json={"text": "mail a@b.com"}).json()
    assert r["blocked"]
    assert c.put("/api/policy", json={"classification": {"NOPE": "PII"}}).status_code == 422
