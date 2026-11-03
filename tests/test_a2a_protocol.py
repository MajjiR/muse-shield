import copy
import time

import pytest

from muse_shield.agent.protocol import AgentIdentity, Capabilities, Directory, Endpoint, ProtocolError
from test_a2a_policy import vc  # noqa: F401  (fixture)


@pytest.fixture
def agents():
    research, finance, eve = AgentIdentity("research"), AgentIdentity("finance"), AgentIdentity("eve")
    d = Directory(research, finance, eve)
    policy = {("research", "finance"): {"AMOUNT"}}
    return Endpoint(research, d, policy), Endpoint(finance, d, policy), Endpoint(eve, d, policy)


def test_signed_envelope_roundtrip_with_a_sealed_amount(vc, agents):
    v, chat = vc
    research, finance, eve = agents
    env = research.build("finance", "conv1", "Is <DEAL_VALUE_1> fair for <DEAL_1>?", vault=v, chat_id=chat, seal_labels=["<DEAL_VALUE_1>"])
    assert "₹120 crore" not in str(env) and env["refs"] == ["<DEAL_1>", "<DEAL_VALUE_1>"]
    got = finance.open(env)
    assert got["values"] == {"<DEAL_VALUE_1>": "₹120 crore"} and got["body"].startswith("Is <DEAL_VALUE_1>")
    eve_copy = {**copy.deepcopy(env), "to": "eve"}  # a third agent can't open it, even re-addressed to itself
    with pytest.raises(ProtocolError):
        eve.open(eve_copy)


def test_tamper_replay_wrong_recipient_and_staleness(vc, agents):
    v, chat = vc
    research, finance, _ = agents
    env = research.build("finance", "c", "hello <PERSON_1>", vault=v, chat_id=chat)
    tampered = {**env, "body": "hello <PERSON_2>"}
    with pytest.raises(ProtocolError, match="bad signature"):
        finance.open(tampered)
    finance.open(env)
    with pytest.raises(ProtocolError, match="replayed"):
        finance.open(env)
    with pytest.raises(ProtocolError, match="addressed"):
        research.open(research.build("finance", "c", "x"))
    old = research.build("finance", "c", "x")
    old["ts"] = time.time() - 3600
    with pytest.raises(ProtocolError):  # old timestamp: signature no longer matches either
        finance.open(old)


def test_policy_and_leak_guard_on_build(vc, agents):
    v, chat = vc
    research, finance, _ = agents
    with pytest.raises(ProtocolError, match="doesn't allow sealing <PERSON_1>"):
        research.build("finance", "c", "x", vault=v, chat_id=chat, seal_labels=["<PERSON_1>"])
    with pytest.raises(ProtocolError, match="doesn't allow"):
        finance.build("research", "c", "x", vault=v, chat_id=chat, seal_labels=["<DEAL_VALUE_1>"])  # policy is one-way
    with pytest.raises(ProtocolError, match="raw values"):
        research.build("finance", "c", "Priya Shah agreed", vault=v, chat_id=chat)


def test_capabilities_single_use_expiry_tamper_scope():
    caps = Capabilities.for_vault(b"\x93" * 32)
    tok = caps.issue("finance", "send_email", "c1", "<PERSON_1>")
    assert caps.redeem(tok, "finance", "send_email")["label"] == "<PERSON_1>"
    with pytest.raises(ProtocolError, match="already used"):
        caps.redeem(tok, "finance", "send_email")
    with pytest.raises(ProtocolError, match="different agent or tool"):
        caps.redeem(caps.issue("finance", "send_email", "c1", "<PERSON_1>"), "eve", "send_email")
    with pytest.raises(ProtocolError, match="expired"):
        caps.redeem(caps.issue("finance", "send_email", "c1", "<PERSON_1>", ttl_s=-1), "finance", "send_email")
    body, mac = caps.issue("finance", "send_email", "c1", "<PERSON_1>").split(".")
    with pytest.raises(ProtocolError, match="signature"):
        caps.redeem(body[:-4] + "AAAA." + mac, "finance", "send_email")
    with pytest.raises(ProtocolError, match="signature"):
        Capabilities.for_vault(b"\x94" * 32).redeem(caps.issue("finance", "send_email", "c1", "<PERSON_1>"), "finance", "send_email")
