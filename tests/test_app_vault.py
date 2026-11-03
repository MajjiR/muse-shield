import sqlite3

import pytest

from muse_shield.app.vault import Vault, VaultError, load_master_key


@pytest.fixture
def vault(tmp_path):
    return Vault(tmp_path / "v.db", b"\x11" * 32)


def test_same_value_same_placeholder_in_chat_and_one_entity_across_chats(vault):
    a, b = vault.create_chat("A"), vault.create_chat("B")
    p1, e1 = vault.entity_placeholder(a, "PERSON", "Sonia Mehta")
    p2, e2 = vault.entity_placeholder(a, "PERSON", "  sonia mehta. ")
    p3, _ = vault.entity_placeholder(a, "PERSON", "Ravi Kumar")
    pb, eb = vault.entity_placeholder(b, "PERSON", "Sonia Mehta")
    assert (p1, p2, p3) == ("<PERSON_1>", "<PERSON_1>", "<PERSON_2>")
    assert e1 == e2 == eb and pb == "<PERSON_1>"
    assert vault.items(a)["entities"][0]["chats"] == 2


def test_role_placeholders_and_1000_inserts_stay_stable(vault):
    c = vault.create_chat()
    assert vault.entity_placeholder(c, "AMOUNT", "10 lakh rupees", base="SALARY")[0] == "<SALARY_1>"
    labels = {vault.entity_placeholder(c, "ID", f"ID-{i % 50}")[0] for i in range(1000)}
    assert len(labels) == 50


def test_contexts_store_full_shape_summary(vault):
    c = vault.create_chat()
    label = vault.add_context(c, "DEAL", "ACQUISITION", "Acme buys Kestrel for 120 crore.", "<ORG_1> buys <ORG_2> for [NUMBER] crore.", "company acquisition")
    assert label == "<DEAL_1>"
    assert vault.resolve(c, label, "shape").startswith("<ORG_1> buys")
    assert vault.resolve(c, label) == "Acme buys Kestrel for 120 crore."
    assert vault.items(c)["contexts"][0]["summary"] == "company acquisition"


def test_mapping_messages_and_graph(vault):
    c = vault.create_chat()
    p, _ = vault.entity_placeholder(c, "PERSON", "Rohan")
    s, _ = vault.entity_placeholder(c, "AMOUNT", "10 lakh rupees", base="SALARY")
    vault.add_message(c, "user", f"My name is {p} and I earn {s}.", original="My name is Rohan and I earn 10 lakh rupees.")
    vault.add_edge(c, s, p, "appears_with")
    vault.add_edge(c, p, s, "appears_with")
    assert vault.mapping(c) == {"<PERSON_1>": "Rohan", "<SALARY_1>": "10 lakh rupees"}
    assert vault.messages(c)[0]["original"].startswith("My name is Rohan")
    g = vault.graph(c)
    assert {n["id"] for n in g["nodes"]} == {"<PERSON_1>", "<SALARY_1>"}
    assert g["edges"] == [{"source": "<PERSON_1>", "target": "<SALARY_1>", "rel": "appears_with", "weight": 2}]


def test_no_plaintext_on_disk_and_tamper_detected(tmp_path):
    v = Vault(tmp_path / "v.db", b"\x22" * 32)
    c = v.create_chat()
    v.entity_placeholder(c, "PERSON", "Zoravar Thakkar")
    v.entity_placeholder(c, "PERSON", "Meenakshi Iyer")
    v.add_message(c, "user", "<PERSON_1>", original="Zoravar Thakkar said hi")
    raw = (tmp_path / "v.db").read_bytes()
    assert b"Zoravar" not in raw and b"zoravar" not in raw
    db = sqlite3.connect(tmp_path / "v.db")
    a, b = db.execute("SELECT id, nonce, value_ct FROM entities ORDER BY created_at").fetchall()
    db.execute("UPDATE entities SET nonce=?, value_ct=? WHERE id=?", (a[1], a[2], b[0]))
    db.commit()
    with pytest.raises(VaultError):
        v.entity_value(b[0])


def test_audit_counts_only_and_consents(vault):
    c = vault.create_chat()
    vault.audit("mask", c, {"PERSON": 2})
    vault.consent(c, "<DEAL_1>", "shape", "allow", "needs deal terms")
    assert vault.audit_rows(c)[0]["counts"] == {"PERSON": 2}
    assert vault.consents(c)[0]["decision"] == "allow"


def test_master_key_file_is_private(tmp_path, monkeypatch):
    monkeypatch.delenv("MUSE_SHIELD_MASTER_KEY", raising=False)
    k = load_master_key(tmp_path / "home")
    assert len(k) == 32 and oct((tmp_path / "home" / "master.key").stat().st_mode)[-3:] == "600"
    monkeypatch.setenv("MUSE_SHIELD_MASTER_KEY", "ab" * 32)
    assert load_master_key(tmp_path / "other") == b"\xab" * 32
