from privacy_engine.detector import Detector
from privacy_engine.masking import SessionAllocator, mask
from privacy_engine.policy import Policy, evaluate


def run(text, allocator=None, policy=None):
    policy = policy or Policy()
    det = Detector().detect(text, terms=policy.terms)
    return mask(text, evaluate(det, policy), allocator or SessionAllocator())


def test_semantic_masking_example():
    r = run("Sarah Chen approved $1.2B for Project Falcon with Northwind Capital.")
    assert r.masked == "PERSON_1 approved MAJOR_TRANSACTION_VALUE for PROJECT_1 with ORG_1."
    assert r.mapping["MAJOR_TRANSACTION_VALUE"] == "$1.2B"
    assert r.mapping["PERSON_1"] == "Sarah Chen"


def test_money_buckets_and_numbering():
    r = run("Confidential: offers of $1.2B and $50M, plus a $250,000 fee and $3,500 expenses.")
    assert "MAJOR_TRANSACTION_VALUE" in r.masked
    assert "LARGE_TRANSACTION_VALUE" in r.masked
    assert "MEDIUM_TRANSACTION_VALUE" in r.masked
    assert "SMALL_TRANSACTION_VALUE" in r.masked
    r2 = run("Bids were $1.2B and $1.5B.")
    assert r2.masked == "Bids were MAJOR_TRANSACTION_VALUE and MAJOR_TRANSACTION_VALUE_2."


def test_same_value_same_token_and_public_untouched():
    r = run("Email bob@corp.io about Meta. Then email bob@corp.io again.")
    assert r.masked == "Email EMAIL_1 about Meta. Then email EMAIL_1 again."


def test_no_original_values_in_masked_text():
    text = "Wire $2,000,000 to IBAN DE89 3704 0044 0532 0130 00 for John Smith (john@smith.dev)."
    r = run(text)
    for original in r.mapping.values():
        assert original not in r.masked
