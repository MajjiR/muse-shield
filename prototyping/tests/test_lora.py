import json

from privacy_engine.detector.llm import SYSTEM_PROMPT, parse_response
from privacy_engine.entities import EntityType as T
from privacy_engine.lora import build_dataset, export
from privacy_engine.personalization import PolicyStore


def test_examples_match_runtime_prompt_and_parser():
    rows = build_dataset(200, seed=1)
    assert len(rows) == 200
    for row in rows:
        system, user, assistant = row["messages"]
        assert system["content"] == SYSTEM_PROMPT
        target = json.loads(assistant["content"])
        ents, _ = parse_response(assistant["content"], user["content"])
        # The runtime parser accepts every gold span (all grounded in the input).
        assert {e["text"] for e in target["entities"]} <= {e.text for e in ents}
    assert any(not json.loads(r["messages"][2]["content"])["confidential"] for r in rows)


def test_taught_terms_and_examples_are_used(tmp_path):
    store = PolicyStore(tmp_path / "p.json")
    store.teach_example("Bluebird ships to Corvane next week.", ["Bluebird"], [], etype=T.PROJECT)
    store.deploy()
    rows = build_dataset(300, seed=2, store=store)
    texts = [r["messages"][1]["content"] for r in rows]
    assert sum("Bluebird" in t for t in texts) > 30
    assert texts.count("Bluebird ships to Corvane next week.") == 3

    info = export(tmp_path / "lora", n=50, store=store)
    assert info == {"train": 45, "val": 5, "dir": str(tmp_path / "lora"), "taught_terms": 1}
    assert len((tmp_path / "lora" / "train.jsonl").read_text().splitlines()) == 45
