import json

import httpx

from muse_shield.backends import GlimmerBackend
from muse_shield.evals import run
from muse_shield.sector_eval import load_cases
from muse_shield.trainset import chat_row


def test_test_rows_become_cases_and_score(tmp_path):
    gold = {"entities": [{"text": "Asha Rao", "type": "PERSON"}, {"text": "₹12 lakh", "type": "AMOUNT", "role": "SALARY"}],
            "contexts": [{"sentences": [2], "kind": "HR", "subtype": "OFFER", "refers_to": None, "summary": "salary offer"}]}
    row = chat_row(["Hi Asha Rao.", "We offer ₹12 lakh a year."], json.dumps(gold))
    (tmp_path / "rows.jsonl").write_text(json.dumps({"messages": row["messages"]}) + "\n")
    (tmp_path / "rows.manifest.jsonl").write_text(json.dumps({"domain": "admin"}) + "\n")
    cases = load_cases(tmp_path)
    assert cases[0].sentences == ["Hi Asha Rao.", "We offer ₹12 lakh a year."] and cases[0].template == "admin"

    def oracle(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(gold)}}], "usage": {}})

    b = GlimmerBackend("https://x.test/v1", "m", "k", client=httpx.Client(transport=httpx.MockTransport(oracle)))
    r = run(b, cases)
    assert r["entities"]["f1"] == 1.0 and r["role_accuracy"] == 1.0 and r["contexts"]["f1"] == 1.0
    assert r["f1_by_template"] == {"admin": 1.0}
