import json

import httpx

from muse_shield import resolution as R
from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.backends import GlimmerBackend

DOC = ("Patient Mohan Das, 71, was discharged on 3 March 2027. He takes metformin 500 mg twice daily.\n\n"
       "BP 150/92 at discharge. Dr. Farah Siddiqui will review him.")
FILL = {"entities": [
    {"id": "PERSON_1", "type": "PERSON", "role": "patient", "mentions": [[1, "Mohan Das"], [2, "He"], [4, "him"]]},
    {"id": "DATE_1", "type": "DATE", "subtype": "EXIT", "owner": "PERSON_1", "mentions": [[1, "3 March 2027"]]},
    {"id": "PERSON_2", "type": "PERSON", "role": "doctor", "mentions": [[4, "Dr. Farah Siddiqui"]]}],
    "relations": [["PERSON_2", "TREATS", "PERSON_1"]]}
CLASSIFY = {"categories": ["medical", "not-a-category"], "summary": "A discharge note for an elderly patient.",
            "extras": [{"text": "metformin 500 mg twice daily", "category": "medical"},
                       {"text": "BP 150/92", "category": "medical"},
                       {"text": "Age", "category": "medical"},              # a field label: dropped
                       {"text": "Mohan Das, 71", "category": "medical"},    # overlaps a name: the fill wins
                       {"text": "not in the text", "category": "medical"}]}


def fake_model(calls: list):
    def handler(request):
        msgs = json.loads(request.content)["messages"]
        if msgs[0]["role"] == "system":  # the fine-tuned fill prompt
            calls.append("fill")
            body = FILL
        else:                            # the classify prompt
            calls.append("classify")
            assert DOC in msgs[0]["content"]
            body = CLASSIFY
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(body)}}],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": 100}})
    chat = GlimmerBackend("https://glimmer.test/v1", "accounts/a/models/er#accounts/a/deployments/d", "k",
                          client=httpx.Client(transport=httpx.MockTransport(handler)), max_tokens=4000)
    return R.ResolutionAnalyzer(chat)


def test_normal_mode_is_one_call_and_unchanged(tmp_path):
    calls = []
    m = Masker(Vault(tmp_path / "v.db", b"\x44" * 32), fake_model(calls)).mask(DOC, "chat-1")
    assert m.analysis_ok, m.error
    assert calls == ["fill"] and m.mode == "normal" and m.categories == []
    assert "metformin" in m.masked_text  # normal mode only masks what the fill finds
    assert "SENSITIVE" not in m.masked_text


def test_classify_mode_adds_categories_and_category_extras(tmp_path):
    calls = []
    m = Masker(Vault(tmp_path / "v.db", b"\x44" * 32), fake_model(calls)).mask(DOC, "chat-1", mode="classify")
    assert m.analysis_ok, m.error
    assert sorted(calls) == ["classify", "fill"] and m.mode == "classify"
    assert m.categories == ["medical"]  # the prompt's valid categories, combined with the rules (TREATS -> medical)
    assert m.summary.startswith("A discharge note")
    assert "metformin" not in m.masked_text and "150/92" not in m.masked_text
    fallback = [s for s in m.spans if s["source"] == "fallback"]
    assert {s["text"] for s in fallback} == {"metformin 500 mg twice daily", "BP 150/92"}
    assert all(s["placeholder"].startswith("<SENSITIVE_") and s["fallback"] == "medical" for s in fallback)
    names = {s["text"]: s["placeholder"] for s in m.spans if s["type"] == "PERSON"}
    assert names["Mohan Das"].startswith("<PERSON_")  # the overlapping extra didn't swallow the name
    assert "He takes <SENSITIVE_1>" in m.masked_text or "He takes <SENSITIVE_2>" in m.masked_text
    assert m.to_dict()["categories"] == ["medical"]


def test_classify_failure_still_masks(tmp_path):
    def handler(request):
        msgs = json.loads(request.content)["messages"]
        content = json.dumps(FILL) if msgs[0]["role"] == "system" else "sorry, I can't"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})
    chat = GlimmerBackend("https://glimmer.test/v1", "m#d", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    m = Masker(Vault(tmp_path / "v.db", b"\x44" * 32), R.ResolutionAnalyzer(chat)).mask(DOC, "chat-1", mode="classify")
    assert m.analysis_ok and "Mohan Das" not in m.masked_text
    assert m.categories == ["medical"]  # the rules still classify it


def test_keep_extra_filters_labels_and_verbs():
    assert not R.keep_extra("Age") and not R.keep_extra("MRN") and not R.keep_extra("thanked")
    assert R.keep_extra("metformin 500 mg") and R.keep_extra("Project Falcon") and R.keep_extra("hypoglycemia")
