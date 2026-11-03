import pytest

from privacy_engine.cloud import CloudLLM, NetworkInspector
from privacy_engine.config import Settings
from privacy_engine.detector import Detector
from privacy_engine.pipeline import PrivacyEngine
from privacy_engine.vault import Vault


@pytest.fixture
def engine(tmp_path):
    settings = Settings(home=tmp_path / "home", cloud_api_key="")
    inspector = NetworkInspector()
    return PrivacyEngine(
        settings,
        vault=Vault(":memory:", b"\x09" * 32),
        detector=Detector(),  # rules only: tests must not depend on a running Ollama
        cloud=CloudLLM("https://unused", "m", inspector=inspector),
    )
