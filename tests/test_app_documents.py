import json
import os
import tempfile
import urllib.parse

import httpx
from doc_fakes import fake_values
from doc_fixtures import TRICKY_DOCX_VALUES, TRICKY_PDF_VALUES, tricky_docx, tricky_pdf
from fastapi.testclient import TestClient

from muse_shield.app.chat import ChatModel
from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_chat import ScriptedModel

def make(tmp_path, replies=(), values=TRICKY_DOCX_VALUES, contexts=None, analyzer=True):
    scripted = ScriptedModel(list(replies))
    model = ChatModel("https://api.meta.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=scripted.transport()))
    vault = Vault(tmp_path / "v.db", b"\x88" * 32)
    app = create_app(vault, fake_values(values, contexts=contexts) if analyzer else None, model, documents_sync=True)
    return TestClient(app), scripted


def upload(c, data, name="Arjun_Malhotra_offer.docx", chat_id=None):
    headers = {"content-type": "application/octet-stream", "x-filename": urllib.parse.quote(name)}
    if chat_id:
        headers["x-chat-id"] = chat_id
    return c.post("/documents", content=data, headers=headers)


def test_upload_masks_verifies_and_downloads(tmp_path):
    c, _ = make(tmp_path)
    r = upload(c, tricky_docx())
    assert r.status_code == 200, r.text
    doc = c.get(f"/documents/{r.json()['doc_id']}").json()
    assert doc["status"] == "ready" and doc["verify"]["ok"] and doc["has_masked_copy"]
    assert doc["counts"]["PERSON"] >= 2 and doc["filename"] == "Arjun_Malhotra_offer.docx"
    dl = c.get(f"/documents/{doc['doc_id']}/masked")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert "PERSON_1_offer.masked.docx" in urllib.parse.unquote(dl.headers["content-disposition"])
    detail = c.get(f"/documents/{doc['doc_id']}", params={"detail": True}).json()
    assert "Dear <PERSON_1>" in detail["masked_text"] and "Arjun Malhotra" in detail["text"]
    assert [d["doc_id"] for d in c.get(f"/chats/{doc['chat_id']}/documents").json()] == [doc["doc_id"]]


def test_chat_over_a_document_sends_only_placeholders(tmp_path):
    c, m = make(tmp_path, ["<PERSON_1> is offered <AMOUNT_1> at <ORG_1>."])
    doc = upload(c, tricky_docx()).json()
    r = c.post("/chat", json={"message": "", "chat_id": doc["chat_id"], "document_ids": [doc["doc_id"]]}).json()
    assert r["error"] == "", r
    assert r["reply"] == "Arjun Malhotra is offered ₹28 lakh at Kestrel Labs."
    body = json.dumps(m.payloads[0], ensure_ascii=False)
    for value in [*TRICKY_DOCX_VALUES, "Arjun_Malhotra_offer"]:
        assert value not in body, value
    assert "[Document 1 · docx" in body
    detail = c.get(f"/chats/{doc['chat_id']}").json()
    card = next(x for x in detail["messages"] if x["role"] == "document")
    assert card["text"] == "" and card["document"]["doc_id"] == doc["doc_id"]


def test_document_attached_once_then_a_question(tmp_path):
    c, m = make(tmp_path, ["First.", "<PERSON_1> starts on 1 Dec 2026."])
    doc = upload(c, tricky_docx()).json()
    c.post("/chat", json={"message": "", "chat_id": doc["chat_id"], "document_ids": [doc["doc_id"]]})
    r = c.post("/chat", json={"message": "When does he start?", "chat_id": doc["chat_id"], "document_ids": [doc["doc_id"]]}).json()
    assert r["error"] == ""
    sent = [x["content"] for x in m.payloads[1]["messages"]]
    assert sum(1 for x in sent if x.startswith("[Document 1")) == 1 and sent[-1] == "When does he start?"


def test_documents_mask_values_not_passages(tmp_path):
    # Spark would mark "Please confirm by Friday." as a passage; in a document that hides too much, so only values go.
    c, _ = make(tmp_path, contexts={"Please confirm": "DECISION"})
    doc = upload(c, tricky_docx()).json()
    detail = c.get(f"/documents/{doc['doc_id']}", params={"detail": True}).json()
    assert "Please confirm by Friday." in detail["masked_text"] and "<DECISION_" not in detail["masked_text"]


def test_need_context_still_works_for_a_value(tmp_path):
    c, m = make(tmp_path, ["NEED_CONTEXT: <PERSON_1> full to address the letter", "Dear Arjun Malhotra,"])
    doc = upload(c, tricky_docx()).json()
    r = c.post("/chat", json={"message": "", "chat_id": doc["chat_id"], "document_ids": [doc["doc_id"]]}).json()
    assert r["ask"] and r["ask"]["label"] == "<PERSON_1>"
    r2 = c.post("/reveal", json={"ask_id": r["ask"]["ask_id"], "decision": "deny"}).json()
    assert r2["error"] == ""


def test_passages_when_asked_for(tmp_path):
    from doc_fakes import fake_values as fv

    from muse_shield.app.engine import Masker
    from muse_shield.documents.pipeline import mask_document

    vault = Vault(tmp_path / "p.db", b"\x99" * 32)
    r = mask_document(tricky_docx(), Masker(vault, fv(TRICKY_DOCX_VALUES, contexts={"Please confirm": "DECISION"})),
                      vault.create_chat(), contexts=True)
    from muse_shield.documents import docx as D
    from muse_shield.documents.ooxml import Package
    from muse_shield.documents.text import build

    again = build(D.blocks(Package(r.data))).text
    assert "<DECISION_1>" in again and "Please confirm" not in again


def test_pdf_with_scanned_page(tmp_path):
    c, _ = make(tmp_path, values=TRICKY_PDF_VALUES)
    doc = c.get(f"/documents/{upload(c, tricky_pdf(), 'offer.pdf').json()['doc_id']}").json()
    assert doc["status"] == "ready" and doc["format"] == "pdf" and doc["pages"] == 3
    assert [p["status"] for p in doc["page_status"]] == ["ok", "ok", "scanned"]


def test_refusals(tmp_path):
    c, _ = make(tmp_path)
    assert upload(c, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64, "old.doc").status_code == 415
    assert upload(c, b"hello", "notes.txt").status_code == 415
    (tmp_path / "off").mkdir()
    off, _ = make(tmp_path / "off", analyzer=False)
    assert upload(off, tricky_docx()).status_code == 503
    other = upload(c, tricky_docx()).json()
    chat_b = upload(c, tricky_docx()).json()["chat_id"]
    r = c.post("/chat", json={"message": "", "chat_id": chat_b, "document_ids": [other["doc_id"]]}).json()
    assert "unknown document" in r["error"]


def test_nothing_readable_on_disk(tmp_path):
    before = set(os.listdir(tempfile.gettempdir()))
    c, _ = make(tmp_path)
    upload(c, tricky_docx())
    raw = (tmp_path / "v.db").read_bytes()
    for value in [*TRICKY_DOCX_VALUES, "Arjun_Malhotra_offer", "Ravi Kumar"]:
        assert value.encode() not in raw, value
    assert set(os.listdir(tempfile.gettempdir())) - before == set()
