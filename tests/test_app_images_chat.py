import json
import urllib.parse

import httpx
from doc_fakes import fake_values
from fastapi.testclient import TestClient

from muse_shield.app.chat import ChatModel
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from muse_shield.images import ImageMasker
from test_app_chat import ScriptedModel
from test_images import FIND, fake_meta, picture

CLEAN = {"text": "", "items": [], "visual": []}
STILL_READABLE = {"text": "Priya Raman", "items": [{"text": "Priya Raman", "type": "PERSON"}], "visual": []}


def make(tmp_path, replies=(), recheck=CLEAN):
    scripted = ScriptedModel(list(replies))
    model = ChatModel("https://api.meta.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=scripted.transport()))
    vault = Vault(tmp_path / "v.db", b"\x66" * 32)
    vision, sam, _ = fake_meta(find=FIND, recheck=recheck)
    app = create_app(vault, fake_values({}), model, image_masker=ImageMasker(vault, vision, sam, refine=False))
    return TestClient(app), scripted, vault


def upload(c, chat_id=None, name="Priya_Raman_badge.png"):
    headers = {"content-type": "application/octet-stream", "x-filename": urllib.parse.quote(name)}
    if chat_id:
        headers["x-chat-id"] = chat_id
    return c.post("/images", content=picture(), headers=headers)


def test_upload_stores_only_the_masked_image(tmp_path):
    c, _, vault = make(tmp_path)
    r = upload(c)
    assert r.status_code == 200, r.text
    info = r.json()
    assert info["verified"] and info["counts"] == {"PERSON": 1, "face": 1} and info["n"] == 1
    assert info["masked_text"] == "NAME <PERSON_1>\nWelcome" and "Priya" not in json.dumps(info["regions"])
    png = c.get(f"/images/{info['image_id']}/masked")
    assert png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    assert [i["image_id"] for i in c.get(f"/chats/{info['chat_id']}/images").json()] == [info["image_id"]]
    raw = (tmp_path / "v.db").read_bytes()
    assert b"Priya" not in raw and b"badge" not in raw


def test_chat_sends_the_masked_picture_and_its_text(tmp_path):
    c, m, _ = make(tmp_path, ["The badge belongs to <PERSON_1>."])
    info = upload(c).json()
    r = c.post("/chat", json={"message": "Whose badge is this?", "chat_id": info["chat_id"], "image_ids": [info["image_id"]]}).json()
    assert r["error"] == "" and r["reply"] == "The badge belongs to Priya Raman."
    sent = m.payloads[0]["messages"]
    image_msg = next(x for x in sent if isinstance(x["content"], list))
    assert image_msg["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "[Image 1" in image_msg["content"][1]["text"] and "<PERSON_1>" in image_msg["content"][1]["text"]
    assert "Priya" not in json.dumps(sent) and "badge.png" not in json.dumps(sent)
    assert r["sent"][1]["content"][0]["image_url"]["url"] == "[masked image]"  # the response doesn't echo the bytes
    card = next(x for x in c.get(f"/chats/{info['chat_id']}").json()["messages"] if x["role"] == "image")
    assert card["image"]["image_id"] == info["image_id"] and card["text"] == ""
    assert c.get("/inspector/audit").json()["clean"]


def test_unverified_image_sends_only_its_text(tmp_path):
    c, m, _ = make(tmp_path, ["Noted."], recheck=STILL_READABLE)
    info = upload(c).json()
    assert info["verified"] is False
    c.post("/chat", json={"message": "", "chat_id": info["chat_id"], "image_ids": [info["image_id"]]})
    assert not any(isinstance(x["content"], list) for x in m.payloads[0]["messages"])


def test_image_from_another_chat_is_refused(tmp_path):
    c, _, vault = make(tmp_path)
    a = upload(c).json()
    other = vault.create_chat()
    r = c.post("/chat", json={"message": "", "chat_id": other, "image_ids": [a["image_id"]]}).json()
    assert "unknown image" in r["error"]
