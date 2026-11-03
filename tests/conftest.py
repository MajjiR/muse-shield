import pytest

import muse_shield.config as config

ENV_KEYS = ["FIREWORKS_API_KEY", "GLIMMER_API_KEY", "GLIMMER_MODEL", "GLIMMER_DEPLOYMENT", "GLIMMER_BASE_URL",
            "MODEL_API_KEY", "META_BASE_URL", "META_SYNTHETIC_ONLY", "MUSE_SPARK_SYNTHETIC_ONLY", "META_REASONING_EFFORT",
            "CLOUD_MODEL", "MUSE_WONDER_MODEL", "ENGINE_BACKEND"]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Tests never read the real .env: no real keys, no real deployment."""
    monkeypatch.setattr(config, "_loaded", True)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
