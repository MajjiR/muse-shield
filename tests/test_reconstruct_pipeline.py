import httpx

from privacy_engine.cloud import CloudLLM
from privacy_engine.entities import EntityType as T
from privacy_engine.policy import Action
from privacy_engine.reconstruct import reconstruct


def test_reconstruct_tolerates_drift_and_flags_unknown():
    m = {"PERSON_1": "Sarah Chen", "MAJOR_TRANSACTION_VALUE": "$1.2B", "MAJOR_TRANSACTION_VALUE_2": "$1.5B"}
    r = reconstruct("Dear [PERSON_1], **person_1** bid MAJOR_TRANSACTION_VALUE_2 vs MAJOR_TRANSACTION_VALUE; PERSON_9 agrees.", m)
    assert r.text == "Dear Sarah Chen, Sarah Chen bid $1.5B vs $1.2B; PERSON_9 agrees."
    assert r.unresolved == ["PERSON_9"]


def test_reconstruct_uses_vault_fallback():
    r = reconstruct("ORG_3 replied", {}, fallback=lambda t: "Globex" if t == "ORG_3" else None)
    assert r.text == "Globex replied" and r.restored == ["ORG_3"]


def test_end_to_end_raw_values_never_on_wire(engine):
    text = "Draft an email to Sarah Chen at sarah@northwind.io about Project Falcon and the $1.2B offer."
    res = engine.ask(text)
    assert not res.error
    sent = engine.inspector.records[-1].request_body
    for raw in ("Sarah Chen", "sarah@northwind.io", "Project Falcon", "$1.2B"):
        assert raw not in sent
    assert "Sarah Chen" in res.answer and "Project Falcon" in res.answer
    assert res.reconstruction.unresolved == []
    assert engine.inspector.summary()["leaks"] == 0


def test_multi_turn_keeps_tokens_consistent(engine):
    first = engine.ask("Summarize the call with John Smith about Acme Corp.")
    second = engine.ask("Now write a note to John Smith.", first.conversation_id)
    assert "PERSON_1" in first.protected.masked.masked
    assert second.protected.masked.masked == "Now write a note to PERSON_1."
    body = engine.inspector.records[-1].request_body
    assert "John" not in body and "Acme" not in body


def test_block_policy_prevents_any_egress(engine):
    engine.policy.type_actions[T.SSN] = Action.BLOCK
    res = engine.ask("My SSN is 123-45-6789, file my taxes")
    assert res.blocked and "SSN" in res.error
    assert len(engine.inspector.records) == 0


def test_cloud_error_is_reported(engine):
    engine.cloud = CloudLLM("https://x", "m", api_key="k", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    res = engine.ask("hello")
    assert res.error.startswith("cloud error")
