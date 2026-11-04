from muse_shield.agent.scenarios import SCENARIOS, render


def test_scenarios_are_well_formed():
    from muse_shield.agent.runners import MOCK_INBOX

    inbox = MOCK_INBOX.read_text()
    assert len(SCENARIOS) == 10 and len({s.id for s in SCENARIOS}) == 10
    for s in SCENARIOS:
        assert s.outcome in ("done", "refused", "none", "any") and s.request
        assert s.setup or s.tool == "read_inbox"
        for addr in s.recipients + s.must_not_send:
            assert any(addr in m for m in s.setup) or addr in inbox, (s.id, addr)
        for value in s.never_seen:
            assert value in inbox, (s.id, value)


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
