import sqlite3

from muse_shield.app.vault import Vault


def make(tmp_path):
    v = Vault(tmp_path / "v.db", b"\x95" * 32)
    for i in range(5):
        v.audit("tool_run", "c1", {"tool": 1, "n": i})
    return v


def test_chain_verifies(tmp_path):
    result = make(tmp_path).verify_audit()
    assert result["ok"] and result["entries"] == 5


def test_editing_an_entry_is_detected(tmp_path):
    v = make(tmp_path)
    db = sqlite3.connect(tmp_path / "v.db")
    db.execute("UPDATE audit_chain SET counts='{\"n\": 99, \"tool\": 1}' WHERE seq=3")
    db.commit()
    assert v.verify_audit() == {"ok": False, "entries": 2, "broken_at": 3}


def test_deleting_an_entry_is_detected(tmp_path):
    v = make(tmp_path)
    db = sqlite3.connect(tmp_path / "v.db")
    db.execute("DELETE FROM audit_chain WHERE seq=2")
    db.commit()
    assert not v.verify_audit()["ok"]


def test_a_different_key_cannot_rebuild_the_chain(tmp_path):
    make(tmp_path)
    assert not Vault(tmp_path / "v.db", b"\x96" * 32).verify_audit()["ok"]
