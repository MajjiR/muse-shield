"""Agent-to-agent envelopes: placeholders in the clear, real values only sealed to one named agent.

    envelope = {v, from, to, conv, nonce, ts, body, refs, sealed[], caps[], sig}

- body      masked text; building an envelope refuses if any raw vault value is in it
- sealed    values the policy lets this recipient see, each encrypted to the recipient's
            X25519 key (ephemeral ECDH -> HKDF -> AES-256-GCM, header bound as AAD).
            Default policy: nothing is sealed.
- caps      capability handles: the right to use a placeholder with one tool, once,
            before an expiry, without seeing its value (HMAC-signed by the vault owner)
- sig       Ed25519 over the canonical envelope; receivers check signer, recipient,
            freshness and nonce reuse (replay)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..app.chat import find_leaks
from ..app.vault import Vault

MAX_AGE_S = 300
B64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
UNB64 = base64.b64decode
RAW = dict(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)

# Which placeholder types an agent may be sent, sealed, per (sender, recipient). Default: nothing.
DEFAULT_SEAL_POLICY: dict[tuple[str, str], set[str]] = {}


class ProtocolError(RuntimeError):
    pass


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass
class AgentIdentity:
    name: str
    sign_key: Ed25519PrivateKey = field(default_factory=Ed25519PrivateKey.generate)
    box_key: X25519PrivateKey = field(default_factory=X25519PrivateKey.generate)

    def public(self) -> dict:
        return {"name": self.name, "sign": B64(self.sign_key.public_key().public_bytes(**RAW)),
                "box": B64(self.box_key.public_key().public_bytes(**RAW))}


class Directory:
    """Who is who: agent name -> public signing and box keys."""

    def __init__(self, *identities: AgentIdentity):
        self.keys = {i.name: i.public() for i in identities}

    def add(self, public: dict) -> None:
        self.keys[public["name"]] = public

    def sign_key(self, name: str) -> Ed25519PublicKey:
        if name not in self.keys:
            raise ProtocolError(f"unknown agent '{name}'")
        return Ed25519PublicKey.from_public_bytes(UNB64(self.keys[name]["sign"]))

    def box_key(self, name: str) -> X25519PublicKey:
        if name not in self.keys:
            raise ProtocolError(f"unknown agent '{name}'")
        return X25519PublicKey.from_public_bytes(UNB64(self.keys[name]["box"]))


def _derive(shared: bytes, aad: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"muse-shield/a2a/seal" + hashlib.sha256(aad).digest()).derive(shared)


def seal(value: str, to_key: X25519PublicKey, aad: bytes) -> dict:
    eph = X25519PrivateKey.generate()
    key = _derive(eph.exchange(to_key), aad)
    nonce = os.urandom(12)
    return {"epk": B64(eph.public_key().public_bytes(**RAW)), "nonce": B64(nonce), "ct": B64(AESGCM(key).encrypt(nonce, value.encode(), aad))}


def unseal(item: dict, my_key: X25519PrivateKey, aad: bytes) -> str:
    key = _derive(my_key.exchange(X25519PublicKey.from_public_bytes(UNB64(item["epk"]))), aad)
    try:
        return AESGCM(key).decrypt(UNB64(item["nonce"]), UNB64(item["ct"]), aad).decode()
    except InvalidTag as exc:
        raise ProtocolError("sealed value can't be opened (not addressed to you, or tampered)") from exc


class Capabilities:
    """Single-use, expiring permissions to use a placeholder with one tool (HMAC-signed, verified locally)."""

    def __init__(self, key: bytes):
        self.key = key
        self.used: set[str] = set()

    @classmethod
    def for_vault(cls, master_key: bytes) -> "Capabilities":
        return cls(HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"muse-shield/a2a/caps").derive(master_key))

    def issue(self, agent: str, tool: str, chat_id: str, label: str, ttl_s: int = 600) -> str:
        claims = {"cap": uuid.uuid4().hex[:16], "agent": agent, "tool": tool, "chat": chat_id, "label": label, "exp": int(time.time()) + ttl_s}
        body = canonical(claims)
        return B64(body) + "." + B64(hmac.new(self.key, body, hashlib.sha256).digest())

    def redeem(self, token: str, agent: str, tool: str) -> dict:
        try:
            body_b64, mac_b64 = token.split(".")
            body = UNB64(body_b64)
        except (ValueError, TypeError) as exc:
            raise ProtocolError("malformed capability") from exc
        if not hmac.compare_digest(UNB64(mac_b64), hmac.new(self.key, body, hashlib.sha256).digest()):
            raise ProtocolError("capability signature doesn't match")
        claims = json.loads(body)
        if claims["exp"] < time.time():
            raise ProtocolError("capability expired")
        if claims["agent"] != agent or claims["tool"] != tool:
            raise ProtocolError("capability is for a different agent or tool")
        if claims["cap"] in self.used:
            raise ProtocolError("capability already used")
        self.used.add(claims["cap"])
        return claims


class Endpoint:
    """One agent's side of the protocol: build and open envelopes."""

    def __init__(self, me: AgentIdentity, directory: Directory, seal_policy: dict | None = None):
        self.me, self.dir = me, directory
        self.seal_policy = DEFAULT_SEAL_POLICY if seal_policy is None else seal_policy
        self.seen: dict[str, float] = {}  # nonce -> ts, for replay protection

    def build(self, to: str, conv: str, body: str, *, vault: Vault | None = None, chat_id: str | None = None,
              seal_labels: list[str] = (), caps: list[str] = ()) -> dict:
        if vault is not None and chat_id is not None:
            leaks = find_leaks(body, vault.mapping(chat_id))
            if leaks:
                raise ProtocolError(f"refusing to send: raw values for {', '.join(leaks)} in the envelope body")
        header = {"v": 1, "from": self.me.name, "to": to, "conv": conv, "nonce": uuid.uuid4().hex, "ts": time.time()}
        sealed = []
        if seal_labels:
            if vault is None or chat_id is None:
                raise ProtocolError("sealing needs the vault")
            allowed = self.seal_policy.get((self.me.name, to), set())
            for label in seal_labels:
                typ = vault.label_type(chat_id, label)
                kind = typ and ("CONTEXT" if typ[0] == "context" else typ[1])
                if kind not in allowed:
                    raise ProtocolError(f"policy doesn't allow sealing {label} ({kind}) to {to}")
                aad = canonical({**header, "label": label})
                sealed.append({"label": label, **seal(vault.resolve(chat_id, label), self.dir.box_key(to), aad)})
        env = {**header, "body": body, "refs": sorted(set(_labels(body))), "sealed": sealed, "caps": list(caps)}
        env["sig"] = B64(self.me.sign_key.sign(canonical(env)))
        return env

    def open(self, env: dict) -> dict:
        """Verify an envelope addressed to me; returns {from, conv, body, refs, values, caps}."""
        if env.get("to") != self.me.name:
            raise ProtocolError("envelope isn't addressed to me")
        sig = env.get("sig")
        unsigned = {k: v for k, v in env.items() if k != "sig"}
        try:
            self.dir.sign_key(env["from"]).verify(UNB64(sig), canonical(unsigned))
        except (InvalidSignature, TypeError, KeyError) as exc:
            raise ProtocolError("bad signature: envelope was tampered with or forged") from exc
        if abs(time.time() - env["ts"]) > MAX_AGE_S:
            raise ProtocolError("envelope too old")
        if env["nonce"] in self.seen:
            raise ProtocolError("replayed envelope")
        self.seen[env["nonce"]] = env["ts"]
        header = {k: env[k] for k in ("v", "from", "to", "conv", "nonce", "ts")}
        values = {s["label"]: unseal(s, self.me.box_key, canonical({**header, "label": s["label"]})) for s in env["sealed"]}
        return {"from": env["from"], "conv": env["conv"], "body": env["body"], "refs": env["refs"], "values": values, "caps": env["caps"]}


def _labels(text: str) -> list[str]:
    from .policy import LABEL

    return LABEL.findall(text)
