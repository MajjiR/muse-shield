import json

import httpx

from muse_shield import resolution as R
from muse_shield.app.engine import Masker, rehydrate
from muse_shield.app.vault import Vault
from muse_shield.backends import GlimmerBackend

DOC = ("Rohan Majji joined Acme Technologies on 3 March 2025. His salary is ₹24 LPA.\n\n"
       "Mr. Majji reports to Sandeep Kumar. Rohan's mother, Lakshmi Majji, is his emergency contact (+91 98450 12345).")


def answer_for(text: str) -> dict:
    """What a correct entity-resolution model returns for the documents in these tests."""
    if text == DOC:
        return {"entities": [
            {"id": "PERSON_1", "type": "PERSON", "role": "employee",
             "mentions": [[1, "Rohan Majji"], [2, "His"], [3, "Mr. Majji"], [4, "Rohan"], [4, "his"]]},
            {"id": "ORG_1", "type": "ORG", "role": "employer", "mentions": [[1, "Acme Technologies"]]},
            {"id": "DATE_1", "type": "DATE", "subtype": "JOINING", "owner": "PERSON_1", "mentions": [[1, "3 March 2025"]]},
            {"id": "SALARY_1", "type": "AMOUNT", "role": "SALARY", "owner": "PERSON_1", "mentions": [[2, "₹24 LPA"]]},
            {"id": "PERSON_2", "type": "PERSON", "role": "manager", "mentions": [[3, "Sandeep Kumar"]]},
            {"id": "PERSON_3", "type": "PERSON", "role": "mother", "mentions": [[4, "Lakshmi Majji"]]},
            {"id": "CONTACT_1", "type": "CONTACT", "subtype": "PHONE", "owner": "PERSON_3", "mentions": [[4, "+91 98450 12345"]]}],
            "relations": [["PERSON_2", "MANAGES", "PERSON_1"], ["PERSON_3", "PARENT_OF", "PERSON_1"]]}
    if text == "Can Rohan start on Monday?":
        return {"entities": [{"id": "PERSON_1", "type": "PERSON", "role": "employee", "mentions": [[1, "Rohan"]]}], "relations": []}
    raise AssertionError(text)


def fake_resolution_model(calls: list):
    def handler(request):
        msgs = json.loads(request.content)["messages"]
        assert len(msgs) == 2  # fine-tuned prompt: system + the document, no worked example
        units = msgs[-1]["content"]
        text = next(t for t in (DOC, "Can Rohan start on Monday?") if R.render_units(t) == units)
        calls.append(text)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer_for(text))}}],
                                         "usage": {"prompt_tokens": 900, "completion_tokens": 300}})
    chat = GlimmerBackend("https://glimmer.test/v1", "accounts/a/models/er#accounts/a/deployments/d", "k",
                          client=httpx.Client(transport=httpx.MockTransport(handler)), max_tokens=4000)
    return R.ResolutionAnalyzer(chat)


def test_one_call_per_document_and_one_placeholder_per_person(tmp_path):
    calls = []
    vault = Vault(tmp_path / "v.db", b"\x44" * 32)
    m = Masker(vault, fake_resolution_model(calls)).mask(DOC, "chat-1")
    assert m.analysis_ok, m.error
    assert len(calls) == 1  # two paragraphs, one call: the model sees the whole text
    labels = {s["text"]: s["placeholder"] for s in m.spans}
    assert labels["Rohan Majji"] == labels["Mr. Majji"] == labels["Rohan"]  # one identity, across paragraphs
    assert labels["Lakshmi Majji"] != labels["Rohan Majji"] and labels["Sandeep Kumar"] != labels["Rohan Majji"]
    assert "His salary is" in m.masked_text and "is his emergency contact" in m.masked_text  # references stay readable
    assert "Majji" not in m.masked_text and "98450" not in m.masked_text
    assert rehydrate(m.masked_text, vault.mapping("chat-1"))[0].count("Rohan Majji") == 3  # restores the full name


def test_owners_and_relations_become_edges(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x44" * 32)
    m = Masker(vault, fake_resolution_model([])).mask(DOC, "chat-1")
    labels = {s["text"]: s["placeholder"] for s in m.spans}
    edges = {(e["source"], e["target"], e["rel"]) for e in vault.graph("chat-1")["edges"]}
    assert (labels["+91 98450 12345"], labels["Lakshmi Majji"], "identifies") in edges  # the mother's phone, not Rohan's
    assert (labels["₹24 LPA"], labels["Rohan Majji"], "belongs_to") in edges
    assert (labels["Sandeep Kumar"], labels["Rohan Majji"], "manages") in edges


def test_first_name_on_a_later_turn_keeps_the_label(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x44" * 32)
    masker = Masker(vault, fake_resolution_model([]))
    first = masker.mask(DOC, "chat-1")
    vault.add_message("chat-1", "user", first.masked_text, DOC)
    later = masker.mask("Can Rohan start on Monday?", "chat-1")
    rohan = next(s["placeholder"] for s in first.spans if s["text"] == "Rohan Majji")
    assert later.masked_text == f"Can {rohan} start on Monday?"


def test_long_text_is_masked_in_parallel_chunks(monkeypatch):
    """A long statement goes to the model in chunks; every chunk's values are found, offsets stay right."""
    from muse_shield.app import engine as eng
    from muse_shield.app.engine import Masker
    from muse_shield.app.vault import Vault
    import tempfile, pathlib

    monkeypatch.setattr(eng, "ER_CHUNK_CHARS", 60)
    monkeypatch.setattr(eng, "ER_CHUNK_CHARS_READ", 60)
    seen = []

    class Fake:
        model = "fake"

        def analyze_document(self, text, paras):
            from muse_shield.analysis import Analysis, Span
            seen.append(text)
            out = []
            for _, p in paras:
                a = Analysis(p, [p])
                for name in ("Asha Rao", "Vikram Shah"):
                    if name in p:
                        a.entities.append(Span(name, "PERSON", p.index(name), p.index(name) + len(name)))
                a.usage = {"prompt_tokens": 1, "completion_tokens": 1}
                out.append(a)
            return out

    text = "\n".join(f"01 Oct  UPI to Asha Rao  ₹{i}00  ref {i}" if i % 2 else f"02 Oct  paid Vikram Shah  ₹{i}50" for i in range(1, 9))
    vault = Vault(pathlib.Path(tempfile.mkdtemp()) / "v.db", b"\x37" * 32)
    m = Masker(vault, Fake()).mask(text, vault.create_chat())
    assert len(seen) > 1 and all(len(t) <= 60 for t in seen)
    assert "Asha Rao" not in m.masked_text and "Vikram Shah" not in m.masked_text
    assert m.masked_text.count("<PERSON_1>") == 4 and m.masked_text.count("<PERSON_2>") == 4
