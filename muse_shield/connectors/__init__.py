"""Connectors: where a tool's data comes from, and where its actions go.

Each module here is one connector with a small backend over a local file (bundled samples of
invented data, or your own files). A real backend (IMAP, CalDAV, Google APIs, an MCP server)
replaces the file reading inside the same functions; nothing above changes, because the
privacy rules live in the tools around them (agent/tools.py, policy.py, executor.py):
  - a read's result is masked before any agent sees it (records are one string each, so a
    name and its address stay together and get linked);
  - addresses learned from a read can't become recipients, except from your own contacts;
  - every send or post needs your confirmation with the real values in front of you.

Point a connector at your own data with MUSE_SHIELD_DATA_DIR (same file names as samples/),
or one file at a time: MUSE_SHIELD_INBOX, MUSE_SHIELD_CONTACTS, MUSE_SHIELD_CALENDAR,
MUSE_SHIELD_FILES, MUSE_SHIELD_CHAT, MUSE_SHIELD_STATEMENT, MUSE_SHIELD_HEALTH.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

SAMPLES = Path(__file__).with_name("samples")


def data_path(name: str, env: str) -> Path:
    """Your file if configured, else the bundled sample."""
    if os.environ.get(env):
        return Path(os.environ[env]).expanduser()
    if os.environ.get("MUSE_SHIELD_DATA_DIR"):
        return Path(os.environ["MUSE_SHIELD_DATA_DIR"]).expanduser() / name
    return SAMPLES / name


def matches(query: str | None, *texts: str) -> bool:
    words = (query or "").casefold().split()
    hay = " ".join(texts).casefold()
    return all(w in hay for w in words)


def opaque_id(*parts: str) -> str:
    """An id that says nothing about the record (file names and UIDs can hold names)."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:10]
