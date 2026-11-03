"""Encrypted local vault: entities, per-chat placeholders, context blocks, messages, graph, audit.

Values never touch disk in plaintext. Every secret column is AES-256-GCM with the row's
identity as associated data, so a ciphertext copied to another row fails to decrypt.
Lookups use an HMAC of the normalized value (value_hash), which also links the same
entity across chats without storing the value.

Key: MUSE_SHIELD_MASTER_KEY (64 hex chars) if set, else a random key file created with
0600 permissions in MUSE_SHIELD_HOME (default ~/.muse-shield).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SCHEMA = """
CREATE TABLE IF NOT EXISTS scopes (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, parent_id TEXT, title TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, value_hash BLOB NOT NULL, nonce BLOB NOT NULL,
    value_ct BLOB NOT NULL, created_at REAL NOT NULL, UNIQUE (type, value_hash)
);
CREATE TABLE IF NOT EXISTS placeholders (
    chat_id TEXT NOT NULL, label TEXT NOT NULL, base TEXT NOT NULL, n INTEGER NOT NULL,
    target_kind TEXT NOT NULL, target_id TEXT NOT NULL, created_at REAL NOT NULL,
    PRIMARY KEY (chat_id, label), UNIQUE (chat_id, target_kind, target_id)
);
CREATE TABLE IF NOT EXISTS contexts (
    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, kind TEXT NOT NULL, subtype TEXT,
    nonce BLOB NOT NULL, payload_ct BLOB NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, role TEXT NOT NULL, masked_text TEXT NOT NULL,
    nonce BLOB, original_ct BLOB, meta TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS edges (
    chat_id TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, rel TEXT NOT NULL, weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (chat_id, src, dst, rel)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, chat_id TEXT, event TEXT NOT NULL, counts TEXT
);
CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, chat_id TEXT NOT NULL, label TEXT NOT NULL,
    level TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT
);
"""

WORKSPACE = "workspace"


class VaultError(RuntimeError):
    pass


def normalize(value: str) -> str:
    """Case, spacing and edge punctuation don't make a different value."""
    return re.sub(r"\s+", " ", value).strip().strip(".,;:!?\"'()[]").casefold()


def load_master_key(home: Path) -> bytes:
    env = os.environ.get("MUSE_SHIELD_MASTER_KEY", "").strip()
    if env:
        key = bytes.fromhex(env)
        if len(key) != 32:
            raise VaultError("MUSE_SHIELD_MASTER_KEY must be 64 hex characters")
        return key
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    path = home / "master.key"
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(os.urandom(32))
    return path.read_bytes()


def default_home() -> Path:
    return Path(os.environ.get("MUSE_SHIELD_HOME", Path.home() / ".muse-shield"))


class _Rows(list):
    """Fully fetched rows, so no cursor is shared between threads."""

    def fetchone(self):
        return self[0] if self else None

    def fetchall(self):
        return list(self)


class _LockedDB:
    """One SQLite connection shared by the server's worker threads: every statement runs under the
    vault lock and is fetched before the lock is released. Without this, a read that lands in the
    middle of another thread's write can come back empty."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn, self._lock = conn, lock

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        with self._lock:
            return _Rows(self._conn.execute(sql, params).fetchall())

    def executescript(self, script: str) -> None:
        with self._lock:
            self._conn.executescript(script)

    def __enter__(self):
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            return self._conn.__exit__(*exc)
        finally:
            self._lock.release()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class Vault:
    def __init__(self, path: Path | str, master_key: bytes):
        if len(master_key) != 32:
            raise VaultError("master key must be 32 bytes")
        sub = lambda info: HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(master_key)  # noqa: E731
        self._aead = AESGCM(sub(b"muse-shield/vault/enc"))
        self._mac = sub(b"muse-shield/vault/value-hash")
        self.path = str(path)
        self._lock = threading.RLock()
        self._db = _LockedDB(sqlite3.connect(self.path, check_same_thread=False), self._lock)
        self._db.execute("PRAGMA secure_delete = ON")  # overwritten rows don't linger in free pages
        self._db.executescript(SCHEMA)
        if self.path != ":memory:":
            os.chmod(self.path, 0o600)
        with self._db:
            self._db.execute("INSERT OR IGNORE INTO scopes VALUES (?, 'workspace', NULL, 'Workspace', ?)", (WORKSPACE, time.time()))

    @classmethod
    def open(cls, home: Path | None = None) -> "Vault":
        home = home or default_home()
        key = load_master_key(home)
        return cls(home / "vault.db", key)

    # -- crypto --------------------------------------------------------------
    def value_hash(self, etype: str, value: str) -> bytes:
        return hmac.new(self._mac, f"{etype}:{normalize(value)}".encode(), hashlib.sha256).digest()

    def _seal(self, aad: str, data: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        return nonce, self._aead.encrypt(nonce, data, aad.encode())

    def _open(self, aad: str, nonce: bytes, ct: bytes) -> bytes:
        try:
            return self._aead.decrypt(nonce, ct, aad.encode())
        except InvalidTag as exc:
            raise VaultError(f"{aad} failed authentication (wrong key or tampered row)") from exc

    # -- chats ---------------------------------------------------------------
    def create_chat(self, title: str = "New chat") -> str:
        chat_id = "c_" + uuid.uuid4().hex[:10]
        with self._lock, self._db:
            self._db.execute("INSERT INTO scopes VALUES (?, 'chat', ?, ?, ?)", (chat_id, WORKSPACE, title, time.time()))
        return chat_id

    def ensure_chat(self, chat_id: str | None, title: str = "New chat") -> str:
        if chat_id and self._db.execute("SELECT 1 FROM scopes WHERE id=? AND kind='chat'", (chat_id,)).fetchone():
            return chat_id
        return self.create_chat(title)

    def title_from_masked(self, chat_id: str, masked_text: str) -> None:
        """Name a new chat after its first masked message (titles are stored in the clear)."""
        title = " ".join(masked_text.split())[:48] or "New chat"
        with self._lock, self._db:
            self._db.execute("UPDATE scopes SET title=? WHERE id=? AND title='New chat'", (title, chat_id))

    def set_title(self, chat_id: str, title: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE scopes SET title=? WHERE id=?", (title, chat_id))

    def chats(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT s.id, s.title, s.created_at, COUNT(m.id) FROM scopes s LEFT JOIN messages m ON m.chat_id = s.id "
            "WHERE s.kind='chat' GROUP BY s.id ORDER BY s.created_at DESC").fetchall()
        return [{"chat_id": r[0], "title": r[1], "created_at": r[2], "messages": r[3]} for r in rows]

    # -- placeholders --------------------------------------------------------
    def _mint(self, chat_id: str, base: str, target_kind: str, target_id: str) -> str:
        with self._lock, self._db:
            row = self._db.execute("SELECT label FROM placeholders WHERE chat_id=? AND target_kind=? AND target_id=?",
                                   (chat_id, target_kind, target_id)).fetchone()
            if row:
                return row[0]
            n = (self._db.execute("SELECT MAX(n) FROM placeholders WHERE chat_id=? AND base=?", (chat_id, base)).fetchone()[0] or 0) + 1
            label = f"<{base}_{n}>"
            self._db.execute("INSERT INTO placeholders VALUES (?,?,?,?,?,?,?)", (chat_id, label, base, n, target_kind, target_id, time.time()))
            return label

    def entity_placeholder(self, chat_id: str, etype: str, value: str, base: str | None = None) -> tuple[str, str]:
        """(placeholder, entity_id). Same normalized value -> same entity everywhere, same label in this chat."""
        vh = self.value_hash(etype, value)
        with self._lock, self._db:
            row = self._db.execute("SELECT id FROM entities WHERE type=? AND value_hash=?", (etype, vh)).fetchone()
            if row:
                entity_id = row[0]
            else:
                entity_id = "e_" + uuid.uuid4().hex[:12]
                nonce, ct = self._seal(f"entity:{entity_id}", value.encode())
                self._db.execute("INSERT INTO entities VALUES (?,?,?,?,?,?)", (entity_id, etype, vh, nonce, ct, time.time()))
        return self._mint(chat_id, base or etype, "entity", entity_id), entity_id

    def add_context(self, chat_id: str, kind: str, subtype: str | None, text: str, shape: str, summary: str) -> str:
        context_id = "x_" + uuid.uuid4().hex[:12]
        payload = json.dumps({"full": text, "shape": shape, "summary": summary}).encode()
        nonce, ct = self._seal(f"context:{context_id}", payload)
        with self._lock, self._db:
            self._db.execute("INSERT INTO contexts VALUES (?,?,?,?,?,?,?)", (context_id, chat_id, kind, subtype, nonce, ct, time.time()))
        return self._mint(chat_id, kind, "context", context_id)

    # -- reads ---------------------------------------------------------------
    def _target(self, chat_id: str, label: str) -> tuple[str, str] | None:
        row = self._db.execute("SELECT target_kind, target_id FROM placeholders WHERE chat_id=? AND label=?", (chat_id, label)).fetchone()
        return (row[0], row[1]) if row else None

    def entity_value(self, entity_id: str) -> str:
        nonce, ct = self._db.execute("SELECT nonce, value_ct FROM entities WHERE id=?", (entity_id,)).fetchone()
        return self._open(f"entity:{entity_id}", nonce, ct).decode()

    def context_payload(self, context_id: str) -> dict:
        nonce, ct = self._db.execute("SELECT nonce, payload_ct FROM contexts WHERE id=?", (context_id,)).fetchone()
        return json.loads(self._open(f"context:{context_id}", nonce, ct))

    def resolve(self, chat_id: str, label: str, level: str = "full") -> str | None:
        """Real value of a placeholder. Context blocks resolve to their full text, shape or summary."""
        target = self._target(chat_id, label)
        if not target:
            return None
        kind, tid = target
        return self.entity_value(tid) if kind == "entity" else self.context_payload(tid)[level]

    def mapping(self, chat_id: str, contexts: str = "full") -> dict[str, str]:
        """label -> real value for every placeholder in the chat (for local rehydration).

        `contexts` picks what a context block resolves to: "full" for the user's own text, "summary" for
        assistant replies, so a whole hidden passage is never pasted into a drafted document."""
        rows = self._db.execute("SELECT label, target_kind, target_id FROM placeholders WHERE chat_id=?", (chat_id,)).fetchall()
        return {label: (self.entity_value(t) if k == "entity" else self.context_payload(t)[contexts]) for label, k, t in rows}

    def items(self, chat_id: str) -> dict:
        """Labels and types for the vault panel; no values."""
        rows = self._db.execute(
            "SELECT p.label, p.base, p.target_kind, p.target_id, COALESCE(e.type, c.kind), c.subtype, p.created_at "
            "FROM placeholders p LEFT JOIN entities e ON p.target_kind='entity' AND e.id=p.target_id "
            "LEFT JOIN contexts c ON p.target_kind='context' AND c.id=p.target_id WHERE p.chat_id=? ORDER BY p.created_at",
            (chat_id,)).fetchall()
        linked = {r[0]: r[1] for r in self._db.execute(
            "SELECT target_id, COUNT(DISTINCT chat_id) FROM placeholders WHERE target_kind='entity' GROUP BY target_id")}
        entities, contexts = [], []
        for label, base, kind, tid, etype, subtype, created in rows:
            if kind == "entity":
                entities.append({"label": label, "type": etype, "base": base, "entity_id": tid, "chats": linked.get(tid, 1)})
            else:
                contexts.append({"label": label, "kind": etype, "subtype": subtype, "summary": self.context_payload(tid)["summary"]})
        return {"entities": entities, "contexts": contexts}

    # -- messages ------------------------------------------------------------
    def add_message(self, chat_id: str, role: str, masked_text: str, original: str | None = None, meta: dict | None = None) -> str:
        message_id = "m_" + uuid.uuid4().hex[:12]
        nonce = ct = None
        if original is not None:
            nonce, ct = self._seal(f"message:{message_id}", original.encode())
        with self._lock, self._db:
            self._db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)",
                             (message_id, chat_id, role, masked_text, nonce, ct, json.dumps(meta or {}), time.time()))
        return message_id

    def messages(self, chat_id: str) -> list[dict]:
        out = []
        for mid, role, masked, nonce, ct, meta, ts in self._db.execute(
                "SELECT id, role, masked_text, nonce, original_ct, meta, created_at FROM messages WHERE chat_id=? ORDER BY created_at", (chat_id,)):
            original = self._open(f"message:{mid}", nonce, ct).decode() if ct else None
            out.append({"message_id": mid, "role": role, "masked_text": masked, "original": original,
                        "meta": json.loads(meta or "{}"), "created_at": ts})
        return out

    # -- graph, audit, consent -----------------------------------------------
    def add_edge(self, chat_id: str, src: str, dst: str, rel: str) -> None:
        if src == dst:
            return
        if rel == "appears_with" and dst < src:
            src, dst = dst, src
        with self._lock, self._db:
            self._db.execute("INSERT INTO edges VALUES (?,?,?,?,1) ON CONFLICT DO UPDATE SET weight = weight + 1", (chat_id, src, dst, rel))

    def members(self, chat_id: str, context_label: str) -> list[str]:
        """Entity placeholders inside a context block (mentioned_in edges)."""
        return [r[0] for r in self._db.execute(
            "SELECT src FROM edges WHERE chat_id=? AND dst=? AND rel='mentioned_in'", (chat_id, context_label))]

    def graph(self, chat_id: str) -> dict:
        items = self.items(chat_id)
        nodes = [{"id": e["label"], "group": "entity", "type": e["type"], "chats": e["chats"]} for e in items["entities"]]
        nodes += [{"id": c["label"], "group": "context", "type": c["kind"], "summary": c["summary"]} for c in items["contexts"]]
        edges = [{"source": s, "target": d, "rel": r, "weight": w}
                 for s, d, r, w in self._db.execute("SELECT src, dst, rel, weight FROM edges WHERE chat_id=?", (chat_id,))]
        return {"nodes": nodes, "edges": edges}

    def audit(self, event: str, chat_id: str | None = None, counts: dict | None = None) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO audit (ts, chat_id, event, counts) VALUES (?,?,?,?)", (time.time(), chat_id, event, json.dumps(counts or {})))

    def audit_rows(self, chat_id: str | None = None) -> list[dict]:
        q = "SELECT ts, chat_id, event, counts FROM audit" + (" WHERE chat_id=?" if chat_id else "") + " ORDER BY id"
        return [{"ts": t, "chat_id": c, "event": e, "counts": json.loads(n or "{}")} for t, c, e, n in self._db.execute(q, (chat_id,) if chat_id else ())]

    def consent(self, chat_id: str, label: str, level: str, decision: str, reason: str = "") -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO consents (ts, chat_id, label, level, decision, reason) VALUES (?,?,?,?,?,?)",
                             (time.time(), chat_id, label, level, decision, reason))

    def consents(self, chat_id: str | None = None) -> list[dict]:
        q = "SELECT ts, chat_id, label, level, decision, reason FROM consents" + (" WHERE chat_id=?" if chat_id else "") + " ORDER BY id"
        return [dict(zip(("ts", "chat_id", "label", "level", "decision", "reason"), r)) for r in self._db.execute(q, (chat_id,) if chat_id else ())]
