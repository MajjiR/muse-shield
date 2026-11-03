from muse_shield.agent.demo import run


def test_two_agent_demo_end_to_end():
    log = run(verbose=False)
    assert not log["ask_on_wire_has_values"]
    assert log["verdict"] == "<DEAL_VALUE_1> is 20% over <BUDGET_1>. Recommend negotiating down before signing <DEAL_1>."
    assert log["outbox"]["to"] == ["priya@kestrel.io"] and log["outbox"]["body"].startswith("Hi Priya Shah, ₹120 crore is 20% over ₹100 crore")
    assert all(v.startswith("rejected") for v in log["attacks"].values()), log["attacks"]
    assert log["audit"]["ok"]
