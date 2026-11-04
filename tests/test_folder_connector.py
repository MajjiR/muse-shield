"""The documents folder: browse by opaque id, read any format masked, and calculate over tables on the device."""

import json
import re

import pytest

from muse_shield.agent.executor import Executor
from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.connectors import folder
from test_connectors import lookup_spark


@pytest.fixture
def ex(tmp_path, monkeypatch):
    for var in ("MUSE_SHIELD_DATA_DIR", "MUSE_SHIELD_FILES"):
        monkeypatch.delenv(var, raising=False)
    vault = Vault(tmp_path / "v.db", b"\x72" * 32)
    return Executor(vault, masker=Masker(vault, lookup_spark())), vault, vault.create_chat()


def entry(executor, chat, name, folder_id=None):
    listing = executor.propose(chat, "list_folder", {"folder_id": folder_id} if folder_id else {}).result["entries"]
    return next(e for e in listing if e["name"] == name)


def test_browse_subfolders_by_opaque_id(ex):
    executor, _, chat = ex
    top = executor.propose(chat, "list_folder", {}).result["entries"]
    assert [e["kind"] for e in top[:3]] == ["folder"] * 3 and all(re.fullmatch(r"[0-9a-f]{10}", e["id"]) for e in top)
    statements = entry(executor, chat, "statements")
    inside = executor.propose(chat, "list_folder", {"folder_id": statements["id"]}).result["entries"]
    assert [e["name"] for e in inside] == ["hdfc 2026 09", "hdfc 2026 10"] and {e["kind"] for e in inside} == {"table"}
    bad = executor.propose(chat, "read_file", {"file_id": "../../etc/passwd"})
    assert bad.status == "failed" and "no file" in bad.error  # only ids from a listing, never paths


def test_a_pdf_receipt_is_read_masked(ex):
    executor, _, chat = ex
    receipt = entry(executor, chat, "apollo pharmacy 2026 10 14", entry(executor, chat, "receipts")["id"])
    a = executor.propose(chat, "read_file", {"file_id": receipt["id"]})
    text = a.result["text"]
    assert "Sunita" not in text and "Kavita" not in text and "1,420.00" not in text and "<PERSON_" in text and "<AMOUNT_" in text


def test_a_table_returns_its_shape_and_masked_samples(ex):
    executor, _, chat = ex
    october = entry(executor, chat, "hdfc 2026 10", entry(executor, chat, "statements")["id"])
    a = executor.propose(chat, "read_file", {"file_id": october["id"]})
    assert a.result["columns"] == "date, description, amount (₹), type, balance (₹)" and a.result["rows"] == "12"
    assert len(a.result["sample"]) == 5 and "Suresh" not in json.dumps(a.result, ensure_ascii=False)


def test_totals_over_a_folder_of_statements_stay_on_the_device(ex):
    executor, vault, chat = ex
    statements = entry(executor, chat, "statements")["id"]
    oct_debits = executor.propose(chat, "query_table", {"source_id": statements, "operation": "sum", "column": "amount",
                                                        "contains": "debit", "contains_column": "type", "month": "2026-10"})
    assert oct_debits.status == "done" and oct_debits.result["result"] == "<RESULT_1>"
    assert vault.mapping(chat)["<RESULT_1>"] == "₹90,528" and "2 files" in oct_debits.result["status"]
    by_merchant = executor.propose(chat, "query_table", {"source_id": statements, "operation": "sum", "column": "amount",
                                                         "contains": "debit", "contains_column": "type",
                                                         "group_by": "description"})
    top = by_merchant.result["groups"][0]
    assert top["group"] == "Rent to <PERSON_1>" and re.fullmatch(r"<RESULT_\d+>", top["value"]) and top["count"] == "2"
    assert vault.mapping(chat)[top["value"]] == "₹76,000"
    assert "76,000" not in json.dumps(by_merchant.for_agent(), ensure_ascii=False)


def test_query_filters_by_a_placeholder_and_counts(ex):
    executor, vault, chat = ex
    statements = entry(executor, chat, "statements")["id"]
    suresh, _ = vault.entity_placeholder(chat, "PERSON", "Suresh Kulkarni")
    rent = executor.propose(chat, "query_table", {"source_id": statements, "operation": "sum", "column": "amount",
                                                  "contains": suresh})
    assert vault.mapping(chat)[rent.result["result"]] == "₹76,000"
    count = executor.propose(chat, "query_table", {"source_id": statements, "operation": "count", "contains": "swiggy"})
    assert count.result["result"] == "3"


def test_query_refuses_mixed_tables_and_bad_columns(ex):
    executor, _, chat = ex
    cards = entry(executor, chat, "cards")["id"]
    a = executor.propose(chat, "query_table", {"source_id": cards, "operation": "sum", "column": "nope"})
    assert a.status == "failed" and "columns: date, merchant, category, amount (₹)" in a.error
    lease = entry(executor, chat, "lease agreement")["id"]
    assert executor.propose(chat, "query_table", {"source_id": lease, "operation": "sum", "column": "x"}).status == "failed"


def test_your_own_folder(ex, tmp_path, monkeypatch):
    executor, vault, chat = ex
    mine = tmp_path / "mine"
    (mine / "bills").mkdir(parents=True)
    (mine / "bills" / "power.csv").write_text("date,amount (₹)\n2026-10-01,1200\n2026-11-01,1350\n")
    (mine / ".secret").write_text("hidden")
    monkeypatch.setenv("MUSE_SHIELD_FILES", str(mine))
    top = executor.propose(chat, "list_folder", {}).result["entries"]
    assert [e["name"] for e in top] == ["bills"]  # hidden files never listed
    bill = folder._entries()
    power = next(k for k, p in bill.items() if p.name == "power.csv")
    total = executor.propose(chat, "query_table", {"source_id": power, "operation": "average", "column": "amount"})
    assert vault.mapping(chat)[total.result["result"]] == "₹1,275"
