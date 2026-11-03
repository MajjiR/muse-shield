import os
import sqlite3

import pytest

from privacy_engine.vault import Vault, VaultError, load_master_key


def test_roundtrip_and_no_plaintext_on_disk(tmp_path):
    v = Vault.open(tmp_path)
    v.put("ns", "PERSON_1", "PERSON", "PERSON", "Sarah Chen")
    v.add_alias("ns", "PERSON:sarah chen", "PERSON_1")
    assert v.reveal("ns", "PERSON_1") == "Sarah Chen"
    assert v.find("ns", "PERSON:sarah chen") == "PERSON_1"
    assert v.find("other", "PERSON:sarah chen") is None
    v.close()
    raw = (tmp_path / "vault.db").read_bytes()
    assert b"Sarah" not in raw and b"sarah" not in raw
    assert oct(os.stat(tmp_path / "vault.key").st_mode)[-3:] == "600"


def test_wrong_key_fails_authentication(tmp_path):
    Vault(tmp_path / "v.db", b"\x01" * 32).put("ns", "EMAIL_1", "EMAIL", "EMAIL", "a@b.co")
    with pytest.raises(VaultError):
        Vault(tmp_path / "v.db", b"\x02" * 32).reveal("ns", "EMAIL_1")


def test_swapped_ciphertext_is_rejected(tmp_path):
    v = Vault(tmp_path / "v.db", b"\x03" * 32)
    v.put("ns", "PERSON_1", "PERSON", "PERSON", "Alice")
    v.put("ns", "PERSON_2", "PERSON", "PERSON", "Bob")
    db = sqlite3.connect(tmp_path / "v.db")
    a = db.execute("SELECT nonce, ciphertext FROM entries WHERE token='PERSON_1'").fetchone()
    db.execute("UPDATE entries SET nonce=?, ciphertext=? WHERE token='PERSON_2'", a)
    db.commit()
    with pytest.raises(VaultError):
        v.reveal("ns", "PERSON_2")


def test_counters_and_ambiguous_alias(tmp_path):
    v = Vault(":memory:", b"\x04" * 32)
    assert [v.next_index("ns", "PERSON") for _ in range(3)] == [1, 2, 3]
    v.add_alias("ns", "PERSON_PART:sarah", "PERSON_1", exclusive=True)
    v.add_alias("ns", "PERSON_PART:sarah", "PERSON_2", exclusive=True)
    assert v.is_ambiguous("ns", "PERSON_PART:sarah")
    assert v.find("ns", "PERSON_PART:sarah") is None


def test_passphrase_key_is_stable(tmp_path):
    assert load_master_key(tmp_path, "hunter2") == load_master_key(tmp_path, "hunter2")
    assert load_master_key(tmp_path, "hunter2") != load_master_key(tmp_path, "other")
