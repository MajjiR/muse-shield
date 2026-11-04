import json

from muse_shield import resolution as R


def test_a_short_mention_skips_the_longer_name_it_sits_in():
    text = "Priya Shah (priya@kestrel.io) leads it, and Priya's salary is up."
    raw = json.dumps({"entities": [{"id": "PERSON_1", "type": "PERSON", "mentions": [[1, "Priya Shah"], [1, "Priya"]]},
                                   {"id": "CONTACT_1", "type": "CONTACT", "mentions": [[1, "priya@kestrel.io"]]}], "relations": []})
    res = R.parse(raw, text)
    starts = [m.start for m in res.entities[0].mentions]
    assert starts == [0, text.index("Priya's")] and res.dropped == 0
    assert "Priya" not in R.mask(res)["masked"]
