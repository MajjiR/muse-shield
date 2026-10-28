"""Settings read from the environment (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


@dataclass
class Settings:
    local_llm_base_url: str = field(default_factory=lambda: _env("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1"))
    local_llm_model: str = field(default_factory=lambda: _env("LOCAL_LLM_MODEL", "llama3.2:1b"))
    # Meta Model API (OpenAI-compatible). Muse Spark reasons over masked text only.
    cloud_base_url: str = field(default_factory=lambda: _env("CLOUD_BASE_URL", "https://api.meta.ai/v1"))
    cloud_model: str = field(default_factory=lambda: _env("CLOUD_MODEL", "muse-spark-1.3"))
    # MODEL_API_KEY is the name Meta's docs use; CLOUD_API_KEY overrides it.
    cloud_api_key: str = field(default_factory=lambda: _env("CLOUD_API_KEY") or _env("MODEL_API_KEY"))
    passphrase: str = field(default_factory=lambda: _env("PRIVACY_ENGINE_PASSPHRASE"))
    home: Path = field(default_factory=lambda: Path(_env("PRIVACY_ENGINE_HOME", ".privacy")))

    def ensure_home(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        os.chmod(self.home, 0o700)
        return self.home
