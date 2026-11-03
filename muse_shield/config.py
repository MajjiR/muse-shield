"""Load settings from the environment and a gitignored .env file (repo root, then cwd).

Keys used:
    FIREWORKS_API_KEY        Muse Glimmer on Fireworks (or GLIMMER_API_KEY for a self-hosted server)
    MODEL_API_KEY            Meta Model API (Muse Spark, Muse Wonder)
    ENGINE_BACKEND           glimmer | muse_spark | muse_wonder
    META_SYNTHETIC_ONLY=1    allow Meta Model API analysis, which sees raw text, on synthetic/public data
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_loaded = False


def load_env(*paths: Path) -> None:
    """Fill os.environ from .env files without overriding variables already set. Idempotent."""
    global _loaded
    if _loaded and not paths:
        return
    for path in paths or (REPO_ROOT / ".env", Path.cwd() / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ.setdefault(key.strip(), value)
    _loaded = True
