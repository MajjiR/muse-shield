from muse_shield.agent.scenarios import SCENARIOS, render


def test_scenarios_are_well_formed():
    from muse_shield.agent.runners import personal
    from muse_shield.connectors import SAMPLES

    samples = "\n".join(p.read_text() for p in SAMPLES.rglob("*") if p.is_file() and p.suffix != ".pdf")
    samples += "\n".join(r["entry"] for r in personal.read_transactions(None, "", {})["transactions"])  # amounts as shown
    assert len(SCENARIOS) == 20 and len({s.id for s in SCENARIOS}) == 20
    for s in SCENARIOS:
        assert s.outcome in ("done", "refused", "none", "any") and s.request
        computed = s.never_seen if s.tool in ("compute", "query_table") else []  # totals worked out on the device
        for value in s.recipients + s.must_not_send + [v for v in s.never_seen if v not in computed]:
            assert any(value in m for m in s.setup) or value in samples, (s.id, value)


def test_render_marks_failures():
    rep = {"scenarios": 1, "rounds": 1, "passed": 0, "total": 1, "leak_free": True, "seconds": 1.0, "cost_usd": 0.01,
           "rows": [{"id": "x", "round": 1, "passed": False, "checks": {"tool": True, "outcome": False}, "tools": ["send_email"],
                     "outcome": "pending", "sent_to": [], "reply": "", "error": "", "violations": []}]}
    out = render(rep)
    assert "**0/1 passed**" in out and "FAIL: outcome" in out


def test_render_lists_shared_asks():
    rep = {"scenarios": 1, "rounds": 1, "passed": 1, "total": 1, "leak_free": True, "seconds": 1.0, "cost_usd": 0.01,
           "rows": [{"id": "x", "round": 1, "passed": True, "checks": {}, "tools": ["send_email"], "outcome": "refused",
                     "sent_to": [], "reply": "Can't send that.", "error": "", "violations": [],
                     "asks": [{"label": "<HR_1>", "level": "shape", "reason": "need the details"}]}]}
    assert "asked for <HR_1> (shape shared)" in render(rep)
