import sqlite3

import httpx
from fastapi.testclient import TestClient

from muse_shield.app.chat import ChatModel
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_mask import ACCEPT, fake_spark
from test_app_mask_modes import DOC, fake_model


def make(tmp_path, replies=("Noted.",)):
    replies = list(replies)
    model = ChatModel("https://api.meta.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": replies.pop(0) if replies else "Noted."}}],
                                            "usage": {"prompt_tokens": 10, "completion_tokens": 2}}))))
    er = fake_model([])
    vault = Vault(tmp_path / "v.db", b"\x55" * 32)
    app = create_app(vault, chat_model=model, modes={"pii_context": (fake_spark(), False), "resolution": (er, False),
                                                     "resolution_classify": (er, True)}, default_mode="resolution")
    return TestClient(app), vault


def test_health_lists_the_three_modes(tmp_path):
    c, _ = make(tmp_path)
    h = c.get("/health").json()
    assert [m["id"] for m in h["modes"]] == ["pii_context", "resolution", "resolution_classify"]
    assert h["default_mode"] == "resolution" and all(m["label"] and m["model"] for m in h["modes"])


def test_each_mode_masks_its_own_way(tmp_path):
    c, vault = make(tmp_path)
    pii = c.post("/chats", json={"mode": "pii_context"}).json()["chat_id"]
    r = c.post("/mask", json={"text": ACCEPT, "chat_id": pii}).json()
    assert r["analysis_ok"] and "<DECISION_1>" in r["masked_text"]  # stage-1 Glimmer: a context block
    er = c.post("/chats", json={"mode": "resolution"}).json()["chat_id"]
    r = c.post("/mask", json={"text": DOC, "chat_id": er}).json()
    assert r["analysis_ok"] and r["categories"] == [] and "metformin" in r["masked_text"]
    r = c.post("/mask", json={"text": DOC, "mode": "resolution_classify"}).json()  # no chat yet: created and locked
    assert r["categories"] == ["medical"] and "metformin" not in r["masked_text"]
    assert vault.chat_mode(r["chat_id"]) == "resolution_classify"
    modes = {ch["chat_id"]: ch["mode"] for ch in c.get("/chats").json()}
    assert modes[pii] == "pii_context" and modes[er] == "resolution"


def test_a_chat_cannot_switch_mode(tmp_path):
    c, vault = make(tmp_path)
    cid = c.post("/chats", json={"mode": "resolution"}).json()["chat_id"]
    assert c.post("/mask", json={"text": DOC, "chat_id": cid}).status_code == 200
    bad = c.post("/mask", json={"text": DOC, "chat_id": cid, "mode": "pii_context"})
    assert bad.status_code == 409 and "start a new chat" in bad.json()["detail"]
    turn = c.post("/chat", json={"message": DOC, "chat_id": cid, "mode": "resolution_classify"}).json()
    assert turn["error"].startswith("Not sent") and "locked" in turn["error"]
    assert vault.chat_mode(cid) == "resolution"
    assert c.get(f"/chats/{cid}").json()["mode"] == "resolution"


def test_unknown_mode_is_refused(tmp_path):
    c, _ = make(tmp_path)
    assert c.post("/chats", json={"mode": "telepathy"}).status_code == 400


def test_a_chat_from_before_modes_locks_to_the_default(tmp_path):
    c, vault = make(tmp_path)
    old = vault.create_chat()  # no mode: like every chat made before this change
    assert vault.chat_mode(old) is None
    assert c.post("/mask", json={"text": DOC, "chat_id": old}).json()["analysis_ok"]
    assert vault.chat_mode(old) == "resolution"


def test_an_old_vault_file_gets_the_mode_column(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE scopes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent_id TEXT, title TEXT, created_at REAL NOT NULL)")
    db.execute("INSERT INTO scopes VALUES ('c_old', 'chat', 'ws', 'Old chat', 1.0)")
    db.commit()
    db.close()
    vault = Vault(path, b"\x55" * 32)
    assert {ch["chat_id"]: ch["mode"] for ch in vault.chats()}["c_old"] is None
    new = vault.create_chat(mode="pii_context")
    assert vault.chat_mode(new) == "pii_context"
    assert vault.lock_chat_mode(new, "resolution") == "pii_context"  # once set, it never changes
