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


# -- Nemotron + synthetic mix -------------------------------------------------

from muse_shield.trainset import benchmark_paragraphs, build_mix, nemotron_rows  # noqa: E402

LEAKED = "Leaked Person was seen at 1 Test Rd."
def _span(text, part, label):
    i = text.index(part)
    return {"start": i, "end": i + len(part), "text": part, "label": label}


def fake_fetch(off, n=100, split="test", tries=5):
    assert split == "train"  # training must never read the benchmark's split
    rows = []
    for i in range(n):
        k = off + i
        street, pin = f"{k} Lake St", f"{7000 + k}"
        text = (f"Asha Varma, born 1990-01-02, lives at {street}.\n\nShe is a nurse and her PIN is {pin}.\n\n"
                + LEAKED + "\n\nNothing private here.")
        spans = [_span(text, "Asha Varma", "first_name"), _span(text, "1990-01-02", "date_of_birth"),
                 _span(text, street, "street_address"), _span(text, "nurse", "occupation"),
                 _span(text, pin, "pin"), _span(text, "Leaked Person", "first_name")]
        rows.append({"uid": f"{k}", "text": text, "domain": f"d{i % 3}", "locale": "us",
                     "document_format": "unstructured", "spans": str(spans)})
    return rows


def _answer(r):
    return json.loads(r["messages"][-1]["content"])


def test_nemotron_rows_cover_new_types_and_skip_benchmark_text():
    rows = nemotron_rows(30, seed=1, exclude={LEAKED}, fetch=fake_fetch, pages=1)
    assert rows and all(LEAKED not in r["messages"][3]["content"] for r in rows)
    types = {e["type"] for r in rows for e in _answer(r)["entities"]}
    assert {"PERSON", "DATE", "ADDRESS", "SENSITIVE_ATTRIBUTE", "SECRET"} <= types
    assert all(_answer(r)["contexts"] == [] for r in rows)
    # Runtime layout: system, worked example, numbered paragraph, gold answer.
    assert [m["role"] for m in rows[0]["messages"]] == ["system", "user", "assistant", "user", "assistant"]
    assert rows[0]["messages"][3]["content"].startswith("Known contexts: none\n[1] ")


def test_empty_paragraphs_are_capped():
    rows = nemotron_rows(40, seed=1, exclude={LEAKED}, fetch=fake_fetch, pages=1, empty_share=0.1)
    empty = sum(not _answer(r)["entities"] for r in rows)
    assert empty <= 4


def test_mix_keeps_contexts_and_excludes_test_paragraphs(tmp_path):
    sample = tmp_path / "test.jsonl"
    sample.write_text(json.dumps({"uid": "t1", "text": "Intro line.\n\n" + LEAKED, "spans": [], "domain": "x",
                                  "locale": "us", "format": "unstructured"}) + "\n")
    assert LEAKED in benchmark_paragraphs(sample)
    rows = build_mix(sample, n_nemotron=20, n_synthetic=20, seed=2, fetch=fake_fetch)
    prompts = [r["messages"][3]["content"] for r in rows]
    assert 30 <= len(rows) <= 40 and len(prompts) == len(set(prompts))  # deduplicated
    assert not any(LEAKED in r["messages"][3]["content"] for r in rows)
    assert any(_answer(r)["contexts"] for r in rows)  # synthetic rows still teach context blocks
