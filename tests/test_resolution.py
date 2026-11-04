import json
import random

import pytest

from muse_shield import resolution as R
from muse_shield import resolution_data as D
from muse_shield.analysis import ContractError

TEXT = ("Rohan Majji joined Acme Technologies as a Software Engineer on 3 March 2025. His annual compensation is ₹24 LPA.\n"
        "He reports to Sandeep Kumar, whose compensation is ₹32 LPA. Rohan's emergency contact is his mother, "
        "Lakshmi Majji (+91 98450 12345).")


def gold_from(res):
    return {"text": res.text, "entities": [{"id": e.id, "type": e.type, "role": e.role, "subtype": e.subtype,
                                            "owner": e.owner, "mentions": [[m.start, m.end] for m in e.mentions]}
                                           for e in res.entities], "relations": [list(r) for r in res.relations]}


def test_example_round_trip_and_mask():
    res = R.parse(R.EXAMPLE_ASSISTANT, TEXT)
    assert res.dropped == 0
    out = R.mask(res)
    assert "Rohan" not in out["masked"] and "Lakshmi" not in out["masked"] and "₹24" not in out["masked"]
    assert "His annual compensation is <SALARY_1>" in out["masked"]  # references stay readable
    salary = next(e for e in out["entities"] if e["placeholder"] == "SALARY_2")
    assert salary["owner"] == "PERSON_2"
    assert R.target_json(TEXT, gold_from(res)) == R.EXAMPLE_ASSISTANT


def test_repeated_pronouns_are_located_in_order():
    text = "Asha met Ravi. He said he would call her and he did."
    raw = json.dumps({"entities": [
        {"id": "PERSON_1", "type": "PERSON", "mentions": [[1, "Asha"], [2, "her"]]},
        {"id": "PERSON_2", "type": "PERSON", "mentions": [[1, "Ravi"], [2, "He"], [2, "he"], [2, "he"]]}], "relations": []})
    res = R.parse(raw, text)
    starts = [m.start for m in res.entities[1].mentions]
    assert starts == sorted(starts) and len(set(starts)) == 4


def test_registry_keeps_identity_across_documents():
    reg = R.Registry()
    a = R.mask(R.parse(json.dumps({"entities": [{"id": "PERSON_1", "type": "PERSON", "mentions": [[1, "Asha Rao"]]}],
                                   "relations": []}), "Asha Rao called."), reg)
    b = R.mask(R.parse(json.dumps({"entities": [{"id": "PERSON_1", "type": "PERSON", "mentions": [[1, "Ravi"]]},
                                                {"id": "PERSON_2", "type": "PERSON", "mentions": [[1, "Asha Rao"]]}],
                                   "relations": []}), "Ravi met Asha Rao."), reg)
    assert a["masked"] == "<PERSON_1> called." and b["masked"] == "<PERSON_2> met <PERSON_1>."


def test_bad_output_raises_and_unknown_owner_is_kept():
    with pytest.raises(ContractError):
        R.parse("not json", TEXT)
    raw = json.dumps({"entities": [{"id": "SALARY_1", "type": "AMOUNT", "role": "SALARY", "owner": "UNKNOWN",
                                    "mentions": [[2, "₹24 LPA"]]}], "relations": []})
    assert R.parse(raw, TEXT).entities[0].owner == "UNKNOWN"


def test_scoring_perfect_and_wrong_owner():
    res = R.parse(R.EXAMPLE_ASSISTANT, TEXT)
    gold = gold_from(res)
    perfect = R.aggregate([R.score_doc(gold, res)])
    assert perfect["coref"]["f1"] == 1.0 and perfect["owner_acc"] == 1.0 and perfect["leak"] == 0.0
    bad = json.loads(R.EXAMPLE_ASSISTANT)
    bad["entities"][3]["owner"] = "PERSON_2"
    assert R.aggregate([R.score_doc(gold, R.parse(json.dumps(bad), TEXT))])["owner_acc"] == 0.75
    none = R.aggregate([R.score_doc(gold, None)])
    assert none["leak"] == 1.0 and none["valid"] == 0.0


def test_check_repairs_writer_output():
    p = D.plan(random.Random(5), "hr_compensation", "t")
    emp = next(e for e in p["entities"] if e["type"] == "PERSON" and e["role"] == "employee")
    first = emp["name"].split()[0]
    pron = "He" if emp["gender"] == "male" else "She"
    others = [e for e in p["entities"] if e["type"] == "PERSON" and e is not emp]
    for o in others:  # keep the pronoun unambiguous for this test
        o["gender"] = "female" if emp["gender"] == "male" else "male"
    vals = [e for e in p["entities"] if e["type"] not in ("PERSON", "ORG")]
    body = " ".join(f"[[{v['key']}|{v['value']}]]." for v in vals if v.get("owner") in (emp["key"], None))
    p["entities"] = [e for e in p["entities"] if e["type"] in ("PERSON", "ORG") or e in vals and e.get("owner") in (emp["key"], None)]
    tagged = (f"Dear [[{emp['key']}|{emp['name']}]], [[{emp['key']}|your]] details: {body} "
              f"{pron} starts soon. {first} will hear from us.")
    gold, why = D.check(p, tagged)
    assert gold, why
    person = next(e for e in gold["entities"] if e["type"] == "PERSON")
    surfaces = [gold["text"][s:t] for s, t in person["mentions"]]
    assert "your" not in surfaces and pron in surfaces and first in surfaces  # 2nd person untagged; pronoun and name auto-tagged
