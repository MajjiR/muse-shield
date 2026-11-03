import json

import httpx
from fastapi.testclient import TestClient

from muse_shield.app.server import create_app
from muse_shield.app.vault import Vault
from test_app_mask import fake_spark

MSG = "Loop in Priya Shah (priya@kestrel.io) and Rohan, his number is +91 98470 12345."
ANSWERS = {MSG: {"entities": [{"text": "Priya Shah", "type": "PERSON"}, {"text": "priya@kestrel.io", "type": "CONTACT"},
                              {"text": "Rohan", "type": "PERSON"}, {"text": "+91 98470 12345", "type": "CONTACT"}], "contexts": []},
           "Email Priya Shah the summary.": {"entities": [{"text": "Priya Shah", "type": "PERSON"}], "contexts": []}}


def test_contacts_link_to_the_nearest_person_and_across_chats(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x91" * 32)
    c = TestClient(create_app(vault, fake_spark(ANSWERS)))
    a = c.post("/mask", json={"text": MSG}).json()
    assert vault.contacts_for(a["chat_id"], "<PERSON_1>") == [{"label": "<CONTACT_1>", "kind": "email", "value": "priya@kestrel.io"}]
    assert vault.contacts_for(a["chat_id"], "<PERSON_2>") == [{"label": "<CONTACT_2>", "kind": "phone", "value": "+91 98470 12345"}]
    # A new chat that only mentions Priya still finds her email through the entity link.
    b = c.post("/mask", json={"text": "Email Priya Shah the summary."}).json()
    found = vault.contacts_for(b["chat_id"], "<PERSON_1>")
    assert [f["value"] for f in found] == ["priya@kestrel.io"] and found[0]["label"].startswith("<CONTACT_")
    assert {"source": "<CONTACT_1>", "target": "<PERSON_1>", "rel": "identifies", "weight": 1} in c.get(f"/chats/{a['chat_id']}/graph").json()["edges"]
