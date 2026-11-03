import json
import re

from muse_shield import results


def report(name, leak):
    return {"backend": name, "model": f"{name}-model", "docs": 5, "leak_rate": leak, "core_leak_rate": leak / 2,
            "span_recall": 1 - leak, "span_precision": 0.9, "type_accuracy": 1.0, "valid_rate": 1.0, "cost_usd": None,
            "recall_by_type": {"PERSON": 0.8, "ID": 0.5}}


def test_save_run_writes_versioned_folder_index_and_readme(tmp_path):
    out = results.save_run("nemotron-pii", "smoke", [report("glimmer", 0.2), report("muse_spark", 0.1)],
                           {"glimmer": [{"uid": "u1", "predictions": []}]}, settings={"glimmer": {"workers": 5}},
                           dataset={"name": "nvidia/Nemotron-PII", "docs": 5}, compare_md="| t |", root=tmp_path)
    assert re.fullmatch(r"\d{8}-\d{6}_v[\d.]+\+[0-9a-z-]+_smoke", out.name)
    for f in ("manifest.json", "glimmer.json", "muse_spark.json", "glimmer.preds.jsonl", "compare.md", "report.html"):
        assert (out / f).exists(), f
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["backends"] == ["glimmer", "muse_spark"] and manifest["git"]
    index = [json.loads(l) for l in (tmp_path / "index.jsonl").read_text().splitlines()]
    assert [r["backend"] for r in index] == ["glimmer", "muse_spark"] and index[0]["settings"] == {"workers": 5}
    readme = (tmp_path / "README.md").read_text()
    assert out.name in readme and "20.0%" in readme


def test_report_html_has_legend_tooltips_table_and_dark_mode():
    page = results.render_html({"run_id": "r", "created": "t", "git": "g", "eval": "nemotron-pii", "tag": "smoke",
                                "dataset": {"name": "d", "docs": 5}}, [report("glimmer", 0.2), report("muse_wonder", 0.12)])
    assert 'class="legend"' in page and "data-tip=" in page and "<details><summary>Table view" in page
    assert "prefers-color-scheme:dark" in page and 'data-theme="dark"' in page
    assert "glimmer · Leak rate: 20.0%" in page and "Recall by PII type" in page


def test_run_id_uses_version_captured_at_start(tmp_path):
    out = results.save_run("nemotron-pii", "t", [report("glimmer", 0.2)], {}, settings={}, dataset={}, compare_md="",
                           root=tmp_path, when=1_700_000_000, git="abc1234")
    assert "+abc1234_t" in out.name
    assert json.loads((out / "manifest.json").read_text())["git"] == "abc1234"
