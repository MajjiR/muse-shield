from privacy_engine.detector import Detector
from privacy_engine.entities import EntityType as T, Sensitivity as S
from privacy_engine.policy import Action, Policy, evaluate
from privacy_engine.values import parse_money


def decide(text, policy=None):
    policy = policy or Policy()
    det = Detector().detect(text, terms=policy.terms, cues=policy.cues)
    return {d.entity.text: (d.sensitivity, d.action) for d in evaluate(det, policy).decisions}


def test_parse_money():
    assert parse_money("$1.2B") == 1.2e9
    assert parse_money("$450,000") == 450_000
    assert parse_money("3 million dollars") == 3e6
    assert parse_money("€20") == 20


def test_public_question_stays_public():
    d = decide("What did Meta announce at Connect? I paid $20 for the ticket.")
    assert d["Meta"] == (S.PUBLIC, Action.ALLOW)
    assert d["$20"] == (S.PUBLIC, Action.ALLOW)


def test_confidential_context_escalates_public_org_and_money():
    d = decide("Confidential: we plan to acquire Meta's AR unit for $40,000.")
    assert d["Meta"] == (S.CONFIDENTIAL, Action.MASK)
    assert d["$40,000"] == (S.CONFIDENTIAL, Action.MASK)


def test_big_money_is_confidential_anywhere():
    assert decide("The fund is $1.2B")["$1.2B"] == (S.CONFIDENTIAL, Action.MASK)


def test_pii_masked_and_type_override_blocks():
    p = Policy(type_actions={T.SSN: Action.BLOCK})
    d = decide("Sarah Chen, SSN 123-45-6789", p)
    assert d["Sarah Chen"] == (S.PII, Action.MASK)
    assert d["123-45-6789"] == (S.PII, Action.BLOCK)


def test_allowlist_and_roundtrip():
    p = Policy(allow_terms=["Northwind Capital"], terms={"Bluebird": T.PROJECT}, cues=["board deck"])
    p2 = Policy.from_dict(p.to_dict())
    assert p2.to_dict() == p.to_dict()
    d = decide("Northwind Capital reviewed Bluebird", p2)
    assert d["Northwind Capital"][0] is S.PUBLIC
    assert d["Bluebird"] == (S.CONFIDENTIAL, Action.MASK)
