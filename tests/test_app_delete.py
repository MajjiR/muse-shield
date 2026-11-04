import sqlite3

from fastapi.testclient import TestClient

from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault

from test_app_mask import ACCEPT, fake_spark


def _counts(path, chat_id):
    db = sqlite3.connect(path)
    return {t: db.execute(f"SELECT COUNT(*) FROM {t} WHERE chat_id=?", (chat_id,)).fetchone()[0]
            for t in ("messages", "placeholders", "contexts", "images")}


def test_delete_chat_removes_everything_but_shared_values_and_audit(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x55" * 32)
    c = TestClient(create_app(vault, fake_spark()))
    first = c.post("/mask", json={"text": ACCEPT}).json()["chat_id"]
    second = c.post("/mask", json={"text": "Ask Rohan to call me."}).json()["chat_id"]  # shares the value "Rohan"
    vault.add_message(first, "user", "<PERSON_1> hi", "Rohan hi")
    img, _ = vault.add_image(first, b"png", {"name": "x.png"}, True, {"PERSON": 1})
    vault.add_message(first, "image", "", meta={"image_id": img})
    assert all(_counts(tmp_path / "v.db", first)[t] for t in ("messages", "placeholders", "contexts", "images"))

    r = c.post(f"/chats/{first}/delete").json()
    assert r["ok"] and r["removed"]["messages"] >= 2 and r["removed"]["images"] == 1
    assert _counts(tmp_path / "v.db", first) == {"messages": 0, "placeholders": 0, "contexts": 0, "images": 0}
    assert first not in {x["chat_id"] for x in c.get("/chats").json()}
    assert c.get(f"/chats/{first}").status_code == 404
    # "Rohan" is still used by the second chat, so its value survives; the salary and address do not
    assert "Rohan" in vault.mapping(second).values()
    assert r["removed"]["entities"] == 2
    assert vault.verify_audit()["ok"]
    assert c.post(f"/chats/{first}/delete").status_code == 404


def test_delete_image_removes_its_message(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x56" * 32)
    c = TestClient(create_app(vault, fake_spark()))
    chat = vault.create_chat()
    img, _ = vault.add_image(chat, b"png", {"name": "x.png"}, True, {})
    vault.add_message(chat, "image", "", meta={"image_id": img})
    assert c.post(f"/images/{img}/delete").json() == {"ok": True}
    assert c.get(f"/images/{img}").status_code == 404
    assert [m for m in c.get(f"/chats/{chat}").json()["messages"] if m["role"] == "image"] == []
    assert c.post(f"/images/{img}/delete").status_code == 404
