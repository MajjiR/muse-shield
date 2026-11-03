from muse_shield.agent.scenarios import SCENARIOS, render


def test_scenarios_are_well_formed():
    assert len(SCENARIOS) == 8 and len({s.id for s in SCENARIOS}) == 8
    for s in SCENARIOS:
        assert s.outcome in ("done", "refused", "none") and s.setup and s.request
        for addr in s.recipients + s.must_not_send:
            assert any(addr in m for m in s.setup), (s.id, addr)


def test_render_marks_failures():
    rep = {"scenarios": 1, "rounds": 1, "passed": 0, "total": 1, "leak_free": True, "seconds": 1.0, "cost_usd": 0.01,
           "rows": [{"id": "x", "round": 1, "passed": False, "checks": {"tool": True, "outcome": False}, "tools": ["send_email"],
                     "outcome": "pending", "sent_to": [], "reply": "", "error": "", "violations": []}]}
    out = render(rep)
    assert "**0/1 passed**" in out and "FAIL: outcome" in out
