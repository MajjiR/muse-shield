import pytest

import muse_shield.config as config

ENV_KEYS = ["FIREWORKS_API_KEY", "GLIMMER_API_KEY", "GLIMMER_MODEL", "GLIMMER_DEPLOYMENT", "GLIMMER_BASE_URL",
            "MODEL_API_KEY", "META_BASE_URL", "META_SYNTHETIC_ONLY", "MUSE_SPARK_SYNTHETIC_ONLY", "META_REASONING_EFFORT", "META_MAX_TOKENS",
            "CLOUD_MODEL", "MUSE_WONDER_MODEL", "ENGINE_BACKEND", "MUSE_SHIELD_MASTER_KEY", "MUSE_SHIELD_HOME", "MUSE_SHIELD_MODEL",
            "MUSE_SHIELD_DEV_RAW_ANALYSIS", "MUSE_SHIELD_ANALYSIS_EFFORT", "MUSE_SHIELD_ANALYZER",
            "MUSE_SHIELD_GLIMMER_MODEL"]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Tests never read the real .env or touch the real vault: no real keys, no ~/.muse-shield."""
    monkeypatch.setattr(config, "_loaded", True)
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MUSE_SHIELD_HOME", str(tmp_path / "muse-home"))
