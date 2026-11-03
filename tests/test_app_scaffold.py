from fastapi.testclient import TestClient

from muse_shield.app.schemas import Ask, ChatResponse, MaskResponse, SpanOut
from muse_shield.app.server import create_app


def test_health():
    r = TestClient(create_app()).get("/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_schemas_match_contract_fields():
    span = SpanOut(start=0, end=5, text="Rohan", type="PERSON", placeholder="<PERSON_1>")
    m = MaskResponse(chat_id="c1", masked_text="<PERSON_1> earns <SALARY_1>.", spans=[span])
    ask = Ask(ask_id="a1", chat_id="c1", label="<DEAL_1>", kind="DEAL", level="shape", preview="<ORG_1> buys <ORG_2>")
    resp = ChatResponse(chat_id="c1", message_id="m1", masked=m, ask=ask)
    assert set(MaskResponse.model_fields) >= {"chat_id", "masked_text", "spans", "contexts", "analysis_ok", "latency_ms"}
    assert resp.model_dump()["ask"]["preview"] == "<ORG_1> buys <ORG_2>"


def test_cors_allows_the_dev_ui_only(tmp_path):
    from muse_shield.app.vault import Vault
    c = TestClient(create_app(Vault(tmp_path / "v.db", b"\x77" * 32)))
    ok = c.options("/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = c.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
