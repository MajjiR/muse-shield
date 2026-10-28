import pytest
from fastapi.testclient import TestClient

from privacy_engine.entities import EntityType as T
from privacy_engine.personalization import DeployBlocked, PolicyStore
from privacy_engine.server import create_app


def test_teach_test_deploy_rollback(engine, tmp_path):
    store = PolicyStore(tmp_path / "p.json")
    text = "Bluebird beta goes to Kestrel Labs next week."
    store.teach_example(text, ["Bluebird"], [], etype=T.PROJECT)
    assert store.draft.terms == {"Bluebird": T.PROJECT}
    assert "terms" in store.diff()

    report = store.test(engine.dry_run)
    taught = next(c for c in report.cases if c.source == "taught")
    assert taught.status == "fixed"
    assert "PROJECT_1" in taught.draft_masked and "Bluebird" in taught.active_masked
    assert report.regressions == 0

    v1 = store.active.version
    store.deploy(report)
    assert store.active.version == v1 + 1 and store.draft is None
    assert PolicyStore(tmp_path / "p.json").active.terms == {"Bluebird": T.PROJECT}  # persisted

    store.rollback()
    assert store.active.terms == {}
    assert store.active.version == v1 + 2


def test_regression_blocks_deploy(engine, tmp_path):
    store = PolicyStore(tmp_path / "p.json")
    store.teach_public("Sarah Chen")  # would leak a builtin case
    report = store.test(engine.dry_run)
    assert report.regressions >= 1
    with pytest.raises(DeployBlocked):
        store.deploy(report)
    store.deploy(report, force=True)
    assert "Sarah Chen" in store.active.allow_terms


def test_teach_api(engine):
    c = TestClient(create_app(engine))
    c.post("/api/teach/term", json={"term": "Bluebird", "type": "PROJECT"})
    c.post("/api/teach/cue", json={"term": "board deck"})
    state = c.get("/api/teach").json()
    assert state["draft"]["terms"] == {"Bluebird": "PROJECT"} and state["draft"]["cues"] == ["board deck"]
    assert c.post("/api/teach/test").json()["summary"]["regressed"] == 0
    assert c.post("/api/teach/deploy", json={}).status_code == 200
    r = c.post("/api/ask", json={"text": "Ship Bluebird"}).json()
    assert r["protected"]["masked"]["masked"] == "Ship PROJECT_1"
    assert c.post("/api/teach/deploy", json={}).status_code == 409  # no draft
