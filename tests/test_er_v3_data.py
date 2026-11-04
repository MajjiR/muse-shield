"""er-v3 data: Nemotron span rows ground as contract docs, the v3 prompt is picked by model name, v3 relabel."""

from muse_shield import er_v3_data as V
from muse_shield import resolution as R


def test_nemotron_row_becomes_contract_doc():
    text = "I, Jason Lee, live in Austin. Jason's site is https://jl.dev and his IP is 10.0.0.7. I work as a nurse."
    spans = [{"start": 3, "end": 8, "label": "first_name"}, {"start": 9, "end": 12, "label": "last_name"},
             {"start": 22, "end": 28, "label": "city"}, {"start": 30, "end": 35, "label": "first_name"},
             {"start": 46, "end": 60, "label": "url"}, {"start": 74, "end": 82, "label": "ipv4"},
             {"start": 94, "end": 99, "label": "occupation"}]
    d = V.nemotron_doc({"uid": "x", "text": text, "spans": spans})
    by_type = {e["id"]: [text[s:t] for s, t in e["mentions"]] for e in d["entities"]}
    assert by_type["PERSON_1"] == ["Jason Lee", "Jason"]  # first+last merged; the lone first name joins them
    assert by_type["LOCATION_1"] == ["Austin"] and by_type["CONTACT_1"] == ["https://jl.dev"]
    assert "nurse" not in str(by_type)  # quasi identifiers (occupation) stay out, as in the core metric
    masked = R.mask(R.parse(R.target_json(text, d), text))["masked"]
    assert "Jason" not in masked and "10.0.0.7" not in masked and "nurse" in masked


def test_prompt_version_and_values_note():
    assert R.prompt_version("accounts/a/models/muse-shield-glimmer-er-v3a-s200") == "v3"
    assert R.prompt_version("accounts/a/models/muse-shield-glimmer-er-v2b") == "v2"
    v3 = R.messages("Hi.", example=False, version="v3", values_only=True)[0]["content"]
    assert "web addresses" in v3 and "Short form" in v3
    assert "web addresses" not in R.messages("Hi.", example=False)[0]["content"]


def test_relabel_adds_places_and_times_and_keeps_owners():
    text = "Ravi Rao moved to Pune. His salary is ₹9 LPA. Call at 10:30 AM."
    doc = {"uid": "u", "family": "f", "text": text, "relations": [],
           "entities": [{"id": "PERSON_1", "type": "PERSON", "mentions": [[0, 8], [24, 27]]},
                        {"id": "SALARY_1", "type": "AMOUNT", "role": "SALARY", "owner": "PERSON_1", "mentions": [[38, 44]]}]}
    out = V.relabel_v3(doc)
    surf = {e["id"]: text[e["mentions"][0][0]:e["mentions"][0][1]] for e in out["entities"]}
    assert surf["LOCATION_1"] == "Pune" and surf["DATE_1"] == "10:30 AM"
    assert next(e for e in out["entities"] if e["id"] == "SALARY_1")["owner"] == "PERSON_1"
