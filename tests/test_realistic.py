import json

import httpx

from muse_shield.backends import GlimmerBackend
from muse_shield.realistic import EXAMPLES, render, run


def test_every_gold_value_is_in_its_text():
    for ex in EXAMPLES:
        for value, _ in ex.must:
            assert value in ex.text, (ex.id, value)
        for value in ex.optional + ex.keep:
            assert value in ex.text, (ex.id, value)
    assert len(EXAMPLES) == 10 and len({ex.id for ex in EXAMPLES}) == 10


def fake(missing=()):
    """Analyzer that returns every gold value it can see, except the ones listed in missing."""
    golds = [(v, t) for ex in EXAMPLES for v, t in ex.must if v not in missing]

    def handler(request):
        msgs = json.loads(request.content)["messages"]
        para = [m["content"] for m in msgs if m["content"].startswith("Known contexts")][-1].split("\n", 1)[1]
        ents = [{"text": v, "type": t, **({"role": "OTHER"} if t == "AMOUNT" else {})} for v, t in golds if v in para]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"entities": ents, "contexts": []})}}],
                                         "usage": {"prompt_tokens": 500, "completion_tokens": 60}})

    return GlimmerBackend("https://x.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_perfect_analyzer_misses_nothing():
    rep = run(1, analyzer=fake())
    assert rep["missed_total"] == 0 and rep["leak_rate"] == 0 and rep["valid_rate"] == 1
    assert all(all(r["kept"].values()) for r in rep["rows"])


def test_misses_are_found_and_counted_per_round():
    rep = run(2, analyzer=fake(missing=("ADHD", "Vikram@2024")))
    assert rep["missed_total"] == 4
    assert {(m["value"], m["times"]) for m in rep["consistent_misses"]} == {("ADHD", 2), ("Vikram@2024", 2)}
    assert rep["missed_by_type"] == {"SENSITIVE_ATTRIBUTE": 2, "SECRET": 2}
    assert "**ADHD** · 2/2" in render(rep)
