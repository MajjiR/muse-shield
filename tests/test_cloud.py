import json

import httpx
import pytest

from privacy_engine.cloud import CloudLLM, NetworkInspector, PrivacyViolation, find_leaks, guard


SECRETS = {"PERSON_1": "Sarah Chen", "PHONE_1": "(415) 555-0134", "MAJOR_TRANSACTION_VALUE": "$1.2B"}


def test_find_leaks_catches_raw_escaped_and_reformatted():
    assert find_leaks("hi PERSON_1", SECRETS) == []
    assert find_leaks("hi sarah chen", SECRETS) == ["PERSON_1"]
    assert find_leaks("call 415.555.0134", SECRETS) == ["PHONE_1"]
    assert find_leaks(json.dumps({"c": "deal at $1.2B"}), SECRETS) == ["MAJOR_TRANSACTION_VALUE"]


def test_guard_refuses_raw_payload():
    with pytest.raises(PrivacyViolation):
        guard([{"role": "user", "content": "email Sarah Chen"}], SECRETS)
    guard([{"role": "user", "content": "email PERSON_1"}], SECRETS)


def test_mock_cloud_records_only_masked_wire_bytes():
    inspector = NetworkInspector()
    cloud = CloudLLM("https://unused", "m", inspector=inspector)
    assert cloud.mock
    reply = cloud.complete([{"role": "user", "content": "Draft an email to PERSON_1 about MAJOR_TRANSACTION_VALUE"}], SECRETS, "c1")
    assert "PERSON_1" in reply
    (rec,) = inspector.records
    assert rec.clean and rec.mock and rec.status == 200
    assert "Sarah" not in rec.request_body
    assert set(rec.tokens_sent) == {"PERSON_1", "MAJOR_TRANSACTION_VALUE"}
    assert inspector.summary()["leaks"] == 0


def test_real_endpoint_receives_masked_payload_and_auth():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok PERSON_1"}}]})

    cloud = CloudLLM("https://api.meta.ai/v1", "muse-spark-1.3", api_key="k", transport=httpx.MockTransport(handler))
    assert not cloud.mock
    assert cloud.complete([{"role": "user", "content": "hi PERSON_1"}], SECRETS) == "ok PERSON_1"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "muse-spark-1.3"
    assert seen["body"]["messages"][0]["role"] == "system"


def test_guard_runs_before_any_bytes_leave():
    inspector = NetworkInspector()
    cloud = CloudLLM("https://unused", "m", inspector=inspector)
    with pytest.raises(PrivacyViolation):
        cloud.complete([{"role": "user", "content": "Sarah Chen"}], SECRETS)
    assert len(inspector.records) == 0
