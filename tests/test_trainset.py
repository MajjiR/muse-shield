import json

from muse_shield.analysis import parse, split_sentences
from muse_shield.evalset import EVAL_POOLS, generate
from muse_shield.trainset import TRAIN_POOLS, _overlap, build, export


def test_train_and_eval_share_no_fillers_or_paragraphs():
    assert _overlap(TRAIN_POOLS, EVAL_POOLS) == set()
    train_users = {json.dumps(r["messages"][3]["content"]) for r in build(300)}
    eval_users = {json.dumps(f"Known contexts: none\n{c.paragraph}") for c in generate(60)}
    assert not train_users & eval_users
    assert not any("MVP Colony" in u for u in train_users)  # acceptance case stays eval-only


def test_rows_match_runtime_prompt_and_contract():
    for r in build(200):
        msgs = r["messages"]
        assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user", "assistant"]
        numbered = msgs[3]["content"].split("\n", 1)[1]
        paragraph = " ".join(part.split("] ", 1)[1] for part in numbered.split(" [") if "] " in part)
        a = parse(msgs[4]["content"], paragraph, split_sentences(paragraph))
        assert a.valid and not a.dropped
        assert all(c.summary for c in a.contexts)


def test_export_files(tmp_path):
    info = export(tmp_path, n=50)
    assert (info["train"], info["val"]) == (45, 5)
    assert info["approx_longest_row_tokens"] < 2048  # Fireworks rejects rows over max-seq-len (default 2048)
    assert len((tmp_path / "train.jsonl").read_text().splitlines()) == 45
