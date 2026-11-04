"""The document eval with a fake analyzer that knows every gold value: everything masked, nothing leaked."""

from doc_fakes import fake_values

from muse_shield import document_eval
from muse_shield.realistic import EXAMPLES


def test_perfect_analyzer_scores_clean():
    values = {v: t for e in EXAMPLES for v, t in e.must}
    rep = document_eval.run(1, analyzer=fake_values(values))
    reports = [document_eval.report_for(rep, f) for f in document_eval.FORMATS]
    for r in reports:
        assert r["span_recall"] == 1.0 and r["leaked_total"] == 0 and r["not_extracted"] == 0, r["backend"]
        assert r["valid_rate"] == 1.0, r["backend"]
        assert r["long_doc_units"] < 15  # packing: the 10-page document is a handful of calls
    assert "| docx |" in document_eval.render(rep, reports)
