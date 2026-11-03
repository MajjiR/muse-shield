import json

import httpx

from muse_shield.backends import GlimmerBackend
from muse_shield.benchmarks.nemotron import LABEL_MAP, Doc, Gold, Pred, paragraphs, parse_row, sample, score
from muse_shield.benchmarks.run import aggregate, render, run_backend

ALL_LABELS = ['account_number', 'age', 'api_key', 'bank_routing_number', 'biometric_identifier', 'blood_type',
              'certificate_license_number', 'city', 'company_name', 'coordinate', 'country', 'county', 'credit_debit_card',
              'customer_id', 'cvv', 'date', 'date_of_birth', 'date_time', 'device_identifier', 'education_level', 'email',
              'employee_id', 'employment_status', 'fax_number', 'first_name', 'gender', 'health_plan_beneficiary_number',
              'http_cookie', 'ipv4', 'ipv6', 'language', 'last_name', 'license_plate', 'mac_address', 'medical_record_number',
              'national_id', 'occupation', 'password', 'phone_number', 'pin', 'political_view', 'postcode', 'race_ethnicity',
              'religious_belief', 'sexuality', 'ssn', 'state', 'street_address', 'swift_bic', 'tax_id', 'time', 'unique_id',
              'url', 'user_name', 'vehicle_identifier']

TEXT = "Brian Cole lives at 146 County Rd 86.\n\nCard 5490 3479 1287 6543, PIN 4421.\nHe is a nurse."
ROW = {"uid": "u1", "text": TEXT, "domain": "Life", "locale": "us", "document_format": "unstructured",
       "spans": str([{"start": 0, "end": 5, "text": "Brian", "label": "first_name"},
                     {"start": 6, "end": 10, "text": "Cole", "label": "last_name"},
                     {"start": 20, "end": 36, "text": "146 County Rd 86", "label": "street_address"},
                     {"start": 44, "end": 63, "text": "5490 3479 1287 6543", "label": "credit_debit_card"},
                     {"start": 69, "end": 73, "text": "4421", "label": "pin"},
                     {"start": 83, "end": 88, "text": "nurse", "label": "occupation"}])}


def test_every_label_is_mapped():
    assert set(ALL_LABELS) <= set(LABEL_MAP)


def test_parse_row_and_paragraph_offsets():
    doc = parse_row(ROW)
    for g in doc.spans:
        assert doc.text[g.start:g.end] == g.text
    paras = paragraphs(doc.text)
    assert [p for _, p in paras] == ["Brian Cole lives at 146 County Rd 86.", "Card 5490 3479 1287 6543, PIN 4421.\nHe is a nurse."]
    for off, p in paras:
        assert doc.text[off:off + len(p)] == p


def test_score_perfect_partial_and_quasi():
    doc = parse_row(ROW)
    perfect = score(doc, [Pred(g.start, g.end, g.text, LABEL_MAP[g.label]) for g in doc.spans])
    assert perfect.leaked_chars == 0 and perfect.pred_on_gold == 6 and perfect.type_ok == 6
    partial = score(doc, [Pred(0, 10, "Brian Cole", "PERSON"), Pred(100, 104, "zzzz", "PERSON")])
    assert partial.gold_found["first_name"] == [1, 1] and partial.gold_found["pin"] == [0, 1]
    assert partial.pred_total == 2 and partial.pred_on_gold == 1
    assert partial.core_gold_chars == partial.gold_chars - 5  # 'nurse' is a quasi-identifier


def test_sample_is_stratified_and_deterministic():
    def fetch(off, n=100, split="test"):
        return [{**ROW, "uid": f"{off}-{i}", "domain": f"d{i % 4}", "locale": ["us", "intl"][i % 2]} for i in range(n)]

    a, b = sample(20, seed=1, pages=3, fetch=fetch), sample(20, seed=1, pages=3, fetch=fetch)
    assert [d.uid for d in a] == [d.uid for d in b] and len(a) == 20
    assert {d.domain for d in a} == {"d0", "d1", "d2", "d3"} and {d.locale for d in a} == {"us", "intl"}


def test_oracle_backend_scores_zero_leak():
    doc = parse_row(ROW)

    def oracle(request):
        para = json.loads(request.content)["messages"][-1]["content"].split("\n", 1)[1]
        ents = [{"text": g.text, "type": LABEL_MAP[g.label]} for g in doc.spans if g.text in para]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"entities": ents, "contexts": []})}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    b = GlimmerBackend("https://x.test/v1", "m", "k", client=httpx.Client(transport=httpx.MockTransport(oracle)))
    report, preds = run_backend(b, [doc], workers=1)
    assert report["leak_rate"] == 0 and report["span_recall"] == 1 and report["span_precision"] == 1
    assert report["valid_rate"] == 1 and report["calls"] == 2 and report["cost_usd"] > 0
    assert "| glimmer `m` | 0.0% |" in render([report], 1)
