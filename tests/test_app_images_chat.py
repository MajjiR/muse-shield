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
    assert "[<IMAGE_1>" in image_msg["content"][1]["text"] and "<PERSON_1>" in image_msg["content"][1]["text"]
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


def test_spark_can_ask_to_see_the_original_picture_and_you_decide(tmp_path):
    import base64
    c, m, vault = make(tmp_path, ["NEED_CONTEXT: <IMAGE_1> full to say who is in the photo", "It's two coaches."])
    info = upload(c).json()
    r = c.post("/chat", json={"message": "Who is this?", "chat_id": info["chat_id"], "image_ids": [info["image_id"]]}).json()
    ask = r["ask"]
    assert ask["kind"] == "image" and ask["label"] == "<IMAGE_1>" and ask["previews"]["full"].endswith("/original")
    original = c.get(ask["previews"]["full"])
    assert original.status_code == 200 and original.content == picture()  # what the card shows is what would be sent
    first = json.dumps(m.payloads[0]["messages"])
    assert base64.b64encode(picture()).decode()[:200] not in first  # nothing unmasked before you allow it
    done = c.post("/reveal", json={"ask_id": ask["ask_id"], "decision": "allow"}).json()
    assert done["reply"] == "It's two coaches."
    second = json.dumps(m.payloads[1]["messages"])
    assert base64.b64encode(picture()).decode()[:200] in second and "allowed you to see the original picture" in second
    assert vault.consents(info["chat_id"])[-1]["label"] == "<IMAGE_1>"
    raw = (tmp_path / "v.db").read_bytes()
    assert b"Priya" not in raw  # the original is kept sealed


def test_declining_keeps_the_original_on_the_device(tmp_path):
    import base64
    c, m, _ = make(tmp_path, ["NEED_CONTEXT: <IMAGE_1> full to say who is in the photo", "From the masked photo: two people."])
    info = upload(c).json()
    ask = c.post("/chat", json={"message": "Who is this?", "chat_id": info["chat_id"], "image_ids": [info["image_id"]]}).json()["ask"]
    done = c.post("/reveal", json={"ask_id": ask["ask_id"], "decision": "deny"}).json()
    assert done["reply"].startswith("From the masked photo")
    assert all(base64.b64encode(picture()).decode()[:200] not in json.dumps(p["messages"]) for p in m.payloads)


def test_deleting_an_image_removes_its_original(tmp_path):
    c, _, vault = make(tmp_path)
    info = upload(c).json()
    assert vault.image_original(info["image_id"]) == picture()
    assert c.post(f"/images/{info['image_id']}/delete").json()["ok"]
    assert vault.image_original(info["image_id"]) is None and c.get(f"/images/{info['image_id']}/original").status_code == 404
