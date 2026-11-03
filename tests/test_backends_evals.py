import json
import re

import httpx
import pytest

from muse_shield.analysis import ContractError, parse, split_sentences
from muse_shield.backends import BackendError, GlimmerBackend, backend_from_env
from muse_shield.evals import render, run
from muse_shield.evalset import generate


def reply(content: str, usage=None) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": usage or {"prompt_tokens": 100, "completion_tokens": 20}})


def last_user(request: httpx.Request) -> str:
    return json.loads(request.content)["messages"][-1]["content"]


def backend(handler) -> GlimmerBackend:
    return GlimmerBackend("https://glimmer.test/v1", "muse-glimmer-30b", "k",
                          client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_evalset_sentences_match_splitter_and_spans_are_grounded():
    for case in generate(60):
        assert split_sentences(case.paragraph) == case.sentences, case.id
        for e in case.entities:
            assert e.text in case.paragraph


def test_acceptance_case_is_first():
    c = generate(1)[0]
    assert c.paragraph == "My name is Rohan and I earn 10 lakh rupees. Tomorrow I'm planning to buy a land at 12-4, MVP Colony, Visakhapatnam."
    assert [(e.type, e.role) for e in c.entities] == [("PERSON", None), ("AMOUNT", "SALARY"), ("ADDRESS", None)]
    assert c.contexts[0].kind == "DECISION" and c.contexts[0].sentences == [2]


def test_parse_drops_hallucinations_and_validates():
    para = "Rohan earns 10 lakh rupees."
    a = parse(json.dumps({"entities": [{"text": "Rohan", "type": "PERSON"}, {"text": "Sita", "type": "PERSON"},
                                       {"text": "10 lakh rupees", "type": "AMOUNT", "role": "salary"}],
                          "contexts": []}), para, [para])
    assert [(s.text, s.start, s.end) for s in a.entities] == [("Rohan", 0, 5), ("10 lakh rupees", 12, 26)]
    assert a.entities[1].role == "SALARY"
    assert a.dropped == [{"text": "Sita", "type": "PERSON"}]
    with pytest.raises(ContractError):
        parse('{"entities": [{"text": "x", "type": "ALIEN"}], "contexts": []}', para, [para])
    with pytest.raises(ContractError):
        parse('{"entities": [], "contexts": [{"sentences": [4], "kind": "DEAL"}]}', para, [para])


def test_request_shape_and_one_retry_on_invalid_json():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["authorization"] == "Bearer k"
        assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0
        if len(calls) == 1:
            return reply("not json")
        return reply('{"entities": [{"text": "Rohan", "type": "PERSON"}], "contexts": []}')

    a = backend(handler).analyze(["Rohan said hi."])[0]
    assert a.valid and a.attempts == 2 and a.usage["prompt_tokens"] == 200
    assert "[1] Rohan said hi." in calls[0]["messages"][-1]["content"]
    assert "broke the contract" in calls[1]["messages"][-1]["content"]


def test_gives_up_after_retry():
    a = backend(lambda r: reply("still not json")).analyze(["x."])[0]
    assert not a.valid and a.attempts == 2 and "invalid JSON" in a.error


def test_muse_spark_backend_refuses_without_synthetic_flag(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.delenv("MUSE_SPARK_SYNTHETIC_ONLY", raising=False)
    with pytest.raises(BackendError, match="synthetic"):
        backend_from_env("muse_spark")
    monkeypatch.setenv("MUSE_SPARK_SYNTHETIC_ONLY", "1")
    assert backend_from_env("muse_spark").name == "muse_spark"


def test_glimmer_defaults_to_fireworks(monkeypatch):
    monkeypatch.setenv("FIREWORKS_API_KEY", "k")
    for var in ("GLIMMER_BASE_URL", "GLIMMER_MODEL", "GLIMMER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    b = backend_from_env("glimmer")
    assert b.base_url == "https://api.fireworks.ai/inference/v1"
    assert b.model == "accounts/fireworks/models/muse-glimmer-30b"


def test_harness_scores_a_perfect_oracle_at_100():
    cases = generate(30)
    by_text = {c.paragraph: c for c in cases}

    def oracle(request):
        numbered = last_user(request).split("\n", 1)[1]
        paragraph = " ".join(re.split(r"\[\d+\] ", numbered)[1:]).replace("  ", " ").strip()
        c = by_text[paragraph]
        return reply(json.dumps({
            "entities": [{"text": e.text, "type": e.type, "role": e.role} for e in c.entities],
            "contexts": [{"sentences": g.sentences, "kind": g.kind, "summary": "x"} for g in c.contexts],
        }))

    r = run(backend(oracle), cases)
    assert r["contract"]["valid_rate"] == 1.0
    assert r["entities"]["f1"] == 1.0 and r["role_accuracy"] == 1.0
    assert r["contexts"]["f1"] == 1.0 and r["hallucinated_spans"] == 0
    assert r["cost_usd"] > 0
    assert "| entity precision / recall / F1 | 100% / 100% / 100% |" in render(r)


def test_harness_counts_misses_and_wrong_roles():
    cases = generate(1)

    def sloppy(request):
        return reply(json.dumps({"entities": [{"text": "Rohan", "type": "PERSON"},
                                              {"text": "10 lakh rupees", "type": "AMOUNT", "role": "PRICE"},
                                              {"text": "Ravi", "type": "PERSON"}],
                                 "contexts": [{"sentences": [2], "kind": "PLAN"}]}))

    r = run(backend(sloppy), cases)
    assert r["entities"]["tp"] == 2 and r["entities"]["fn"] == 1  # address missed
    assert r["role_accuracy"] == 0.0
    assert r["hallucinated_spans"] == 1
    assert r["contexts"]["tp"] == 0 and r["context_kind_accuracy"] == 0.0
