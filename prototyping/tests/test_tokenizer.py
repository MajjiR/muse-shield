import pytest

from privacy_engine.detector import Detector
from privacy_engine.entities import Entity, EntityType as T
from privacy_engine.masking import mask
from privacy_engine.policy import Policy, evaluate
from privacy_engine.tokenizer import VaultAllocator
from privacy_engine.vault import Vault


@pytest.fixture
def alloc():
    return VaultAllocator(Vault(":memory:", b"\x07" * 32), namespace="test")


def tok(alloc, text, etype):
    return alloc.token_for(Entity(text, etype, 0, len(text)))


def test_person_aliases(alloc):
    assert tok(alloc, "Sarah Chen", T.PERSON) == "PERSON_1"
    assert tok(alloc, "sarah chen", T.PERSON) == "PERSON_1"
    assert tok(alloc, "Ms. Chen", T.PERSON) == "PERSON_1"
    assert tok(alloc, "Sarah", T.PERSON) == "PERSON_1"
    assert tok(alloc, "John Smith", T.PERSON) == "PERSON_2"


def test_ambiguous_first_name_gets_new_token(alloc):
    tok(alloc, "Sarah Chen", T.PERSON)
    tok(alloc, "Sarah Patel", T.PERSON)
    assert tok(alloc, "Sarah", T.PERSON) == "PERSON_3"
    assert tok(alloc, "Patel", T.PERSON) == "PERSON_2"


def test_org_money_phone_normalization(alloc):
    assert tok(alloc, "Acme Corp", T.ORG) == tok(alloc, "Acme Corp.", T.ORG) == tok(alloc, "ACME", T.ORG)
    assert tok(alloc, "$1.2B", T.MONEY) == tok(alloc, "$1,200,000,000", T.MONEY) == "MAJOR_TRANSACTION_VALUE"
    assert tok(alloc, "(415) 555-0134", T.PHONE) == tok(alloc, "+1 415.555.0134", T.PHONE)


def test_tokens_persist_across_conversations(tmp_path):
    def masked(text):
        v = Vault(tmp_path / "v.db", b"\x08" * 32)
        p = Policy()
        r = mask(text, evaluate(Detector().detect(text), p), VaultAllocator(v))
        v.close()
        return r

    first = masked("Draft a memo from Sarah Chen to John Smith.")
    second = masked("What did John Smith say to Dr. Chen?")
    assert first.masked == "Draft a memo from PERSON_1 to PERSON_2."
    assert second.masked == "What did PERSON_2 say to PERSON_1?"


def test_reveal(alloc):
    t = tok(alloc, "Northwind Capital", T.ORG)
    assert alloc.reveal(t) == "Northwind Capital"
