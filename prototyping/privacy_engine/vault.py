"""Encrypted local token vault.

Token -> original value lives only on this device, in SQLite, encrypted with
AES-256-GCM. Lookups ("have we seen this person before?") go through an HMAC of
the normalized value, so the vault can find a token without decrypting
everything and without storing any plaintext. The token is bound into each
ciphertext as associated data, so swapping rows on disk fails to decrypt.

Key material: a passphrase (scrypt) if PRIVACY_ENGINE_PASSPHRASE is set,
otherwise a random 256-bit key file created with 0600 permissions.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    namespace  TEXT NOT NULL,
    token      TEXT NOT NULL,
    label      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    nonce      BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (namespace, token)
);
CREATE TABLE IF NOT EXISTS aliases (
    namespace TEXT NOT NULL,
    lookup    BLOB NOT NULL,
    token     TEXT,            -- NULL marks an ambiguous alias (two entities share it)
    PRIMARY KEY (namespace, lookup)
);
CREATE TABLE IF NOT EXISTS counters (
    namespace TEXT NOT NULL,
    label     TEXT NOT NULL,
    n         INTEGER NOT NULL,
    PRIMARY KEY (namespace, label)
);
"""


class VaultError(RuntimeError):
    pass


def load_master_key(home: Path, passphrase: str = "") -> bytes:
    home.mkdir(parents=True, exist_ok=True)
    if passphrase:
        salt_path = home / "vault.salt"
        if not salt_path.exists():
            salt_path.write_bytes(os.urandom(16))
            os.chmod(salt_path, 0o600)
        return Scrypt(salt=salt_path.read_bytes(), length=32, n=2**15, r=8, p=1).derive(passphrase.encode())
    key_path = home / "vault.key"
    if not key_path.exists():
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(os.urandom(32))
    return key_path.read_bytes()


def _subkey(master: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(master)


@dataclass
class VaultEntry:
    namespace: str
    token: str
    label: str
    kind: str
    created_at: float

    def to_dict(self) -> dict:
        return {"namespace": self.namespace, "token": self.token, "label": self.label, "kind": self.kind, "created_at": self.created_at}


class Vault:
    def __init__(self, path: Path | str, master_key: bytes):
        if len(master_key) != 32:
            raise VaultError("master key must be 32 bytes")
        self.path = str(path)
        self._aead = AESGCM(_subkey(master_key, b"privacy-engine/vault/enc"))
        self._mac_key = _subkey(master_key, b"privacy-engine/vault/lookup")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        if self.path != ":memory:":
            os.chmod(self.path, 0o600)

    @classmethod
    def open(cls, home: Path, passphrase: str = "") -> "Vault":
        return cls(home / "vault.db", load_master_key(home, passphrase))

    # -- lookups -------------------------------------------------------------
    def _lookup(self, key: str) -> bytes:
        return hmac.new(self._mac_key, key.encode(), hashlib.sha256).digest()

    def find(self, namespace: str, key: str) -> str | None:
        row = self._db.execute(
            "SELECT token FROM aliases WHERE namespace=? AND lookup=?", (namespace, self._lookup(key))
        ).fetchone()
        return row[0] if row else None

    def add_alias(self, namespace: str, key: str, token: str, *, exclusive: bool = False) -> None:
        """Map an alias to a token. With exclusive=True, a clash marks the alias ambiguous."""
        lookup = self._lookup(key)
        with self._lock, self._db:
            row = self._db.execute("SELECT token FROM aliases WHERE namespace=? AND lookup=?", (namespace, lookup)).fetchone()
            if row is None:
                self._db.execute("INSERT INTO aliases VALUES (?,?,?)", (namespace, lookup, token))
            elif exclusive and row[0] not in (token, None):
                self._db.execute("UPDATE aliases SET token=NULL WHERE namespace=? AND lookup=?", (namespace, lookup))

    def is_ambiguous(self, namespace: str, key: str) -> bool:
        row = self._db.execute(
            "SELECT token FROM aliases WHERE namespace=? AND lookup=?", (namespace, self._lookup(key))
        ).fetchone()
        return row is not None and row[0] is None

    # -- entries -------------------------------------------------------------
    def next_index(self, namespace: str, label: str) -> int:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO counters VALUES (?,?,1) ON CONFLICT(namespace,label) DO UPDATE SET n=n+1",
                (namespace, label),
            )
            return self._db.execute("SELECT n FROM counters WHERE namespace=? AND label=?", (namespace, label)).fetchone()[0]

    def put(self, namespace: str, token: str, label: str, kind: str, value: str) -> None:
        nonce = os.urandom(12)
        ct = self._aead.encrypt(nonce, value.encode(), f"{namespace}/{token}".encode())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO entries VALUES (?,?,?,?,?,?,?)", (namespace, token, label, kind, nonce, ct, time.time())
            )

    def reveal(self, namespace: str, token: str) -> str | None:
        row = self._db.execute(
            "SELECT nonce, ciphertext FROM entries WHERE namespace=? AND token=?", (namespace, token)
        ).fetchone()
        if row is None:
            return None
        try:
            return self._aead.decrypt(row[0], row[1], f"{namespace}/{token}".encode()).decode()
        except InvalidTag as exc:
            raise VaultError(f"vault entry {token} failed authentication (wrong key or tampered)") from exc

    def entries(self, namespace: str | None = None) -> list[VaultEntry]:
        q = "SELECT namespace, token, label, kind, created_at FROM entries"
        rows = self._db.execute(q + " WHERE namespace=? ORDER BY created_at", (namespace,)) if namespace else self._db.execute(q + " ORDER BY created_at")
        return [VaultEntry(*r) for r in rows]

    def wipe(self, namespace: str | None = None) -> None:
        with self._lock, self._db:
            for table in ("entries", "aliases", "counters"):
                if namespace:
                    self._db.execute(f"DELETE FROM {table} WHERE namespace=?", (namespace,))
                else:
                    self._db.execute(f"DELETE FROM {table}")

    def close(self) -> None:
        self._db.close()
