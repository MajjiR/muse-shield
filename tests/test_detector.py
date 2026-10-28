import json

import httpx

from privacy_engine.detector import Detector, LlamaDetector
from privacy_engine.detector.rules import luhn_ok
from privacy_engine.entities import EntityType as T


def types(det):
    return {(e.text, e.type) for e in det.entities}


def test_structured_identifiers():
    text = (
        "Email sarah.chen@acme.io or call (415) 555-0134. SSN 123-45-6789, card 4111 1111 1111 1111, "
        "server 10.0.4.17, key sk-proj-abcdefghijklmnopqrstuv."
    )
    found = types(Detector().detect(text))
    assert ("sarah.chen@acme.io", T.EMAIL) in found
    assert ("(415) 555-0134", T.PHONE) in found
    assert ("123-45-6789", T.SSN) in found
    assert ("4111 1111 1111 1111", T.CREDIT_CARD) in found
    assert ("10.0.4.17", T.IP_ADDRESS) in found
    assert ("sk-proj-abcdefghijklmnopqrstuv", T.API_KEY) in found


def test_name_after_capitalized_word():
    assert ("John Smith", T.PERSON) in types(Detector().detect("Email John Smith today"))


def test_luhn_rejects_random_digits():
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")


def test_names_orgs_money_projects():
    text = "Sarah Chen told Dr. Patel that Northwind Capital will pay $1.2B for Project Falcon."
    found = types(Detector().detect(text))
    assert ("Sarah Chen", T.PERSON) in found
    assert ("Dr. Patel", T.PERSON) in found
    assert ("Northwind Capital", T.ORG) in found
    assert ("$1.2B", T.MONEY) in found
    assert ("Project Falcon", T.PROJECT) in found


def test_confidential_context():
    det = Detector().detect("Confidential: we are acquiring Meta's AR unit before it is announced.")
    assert det.context.confidential
    assert not Detector().detect("What did Meta announce at Connect?").context.confidential


def test_taught_terms():
    det = Detector().detect("Bluebird ships in Q3", terms={"Bluebird": T.PROJECT})
    assert ("Bluebird", T.PROJECT) in types(det)


def _fake_ollama(reply: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama3.2:1b"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_llama_spans_are_grounded_and_merged():
    reply = {
        "entities": [
            {"text": "Kestrel", "type": "PROJECT"},
            {"text": "Globex", "type": "ORG"},
            {"text": "Hallucinated Person", "type": "PERSON"},  # not in text -> dropped
            {"text": "sarah@x.com", "type": "PERSON"},  # rules' EMAIL wins the overlap
        ],
        "confidential": True,
        "reason": "unreleased roadmap",
    }
    llama = LlamaDetector("http://local/v1", "llama3.2:1b", client=_fake_ollama(reply))
    det = Detector(llama).detect("Kestrel launches with Globex; ping sarah@x.com")
    found = types(det)
    assert ("Kestrel", T.PROJECT) in found
    assert ("Globex", T.ORG) in found
    assert ("sarah@x.com", T.EMAIL) in found
    assert not any(t == "Hallucinated Person" for t, _ in found)
    assert det.context.confidential
    assert "llama:llama3.2:1b" in det.backends


def test_llama_down_falls_back_to_rules():
    def handler(request):
        raise httpx.ConnectError("refused")

    llama = LlamaDetector("http://local/v1", "m", client=httpx.Client(transport=httpx.MockTransport(handler)))
    det = Detector(llama).detect("mail bob@corp.com")
    assert det.backends == ["rules"]
    assert ("bob@corp.com", T.EMAIL) in types(det)
