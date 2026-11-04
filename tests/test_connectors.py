"""Every connector over its bundled sample data: reads come back masked, actions follow the same rules as email."""

import json
import re

import httpx
import pytest

from muse_shield.agent.executor import Executor
from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.backends import GlimmerBackend
from muse_shield.connectors.compute import evaluate, to_python

NAMES = {"Rahul Mehta": "PERSON", "Ananya Iyer": "PERSON", "Meera Pillai": "PERSON", "Priya Shah": "PERSON",
         "Kavita Rao": "PERSON", "Sunita Verma": "PERSON", "Suresh Kulkarni": "PERSON", "Arjun Nair": "PERSON",
         "Karan Mehta": "PERSON", "Brightpath Studio": "ORG", "Kestrel Labs": "ORG", "thyroid": "SENSITIVE_ATTRIBUTE"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RUPEES = re.compile(r"(?:₹|Rs\. )\d[\d,]*(?:\.\d+)?(?: lakh| crore)?")


def lookup_spark():
    """A fake analyzer that finds the made-up names, any email and any rupee amount in whatever it's given."""
    def handler(request):
        msgs = json.loads(request.content)["messages"]
        para = [m["content"] for m in msgs if m["content"].startswith("Known contexts")][-1].split("\n", 1)[1]
        para = " ".join(part.split("] ", 1)[1] for part in para.split(" [") if "] " in part)
        ents = [{"text": n, "type": t} for n, t in NAMES.items() if n in para]
        ents += [{"text": m, "type": "CONTACT"} for m in EMAIL.findall(para)]
        ents += [{"text": m, "type": "AMOUNT"} for m in RUPEES.findall(para)]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"entities": ents, "contexts": []})}}],
                                         "usage": {"prompt_tokens": 300, "completion_tokens": 40}})
    return GlimmerBackend("https://spark.test/v1", "muse-spark-1.3", "k", client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def ex(tmp_path, monkeypatch):
    for var in ("MUSE_SHIELD_DATA_DIR", "MUSE_SHIELD_INBOX"):
        monkeypatch.delenv(var, raising=False)
    vault = Vault(tmp_path / "v.db", b"\x71" * 32)
    executor = Executor(vault, masker=Masker(vault, lookup_spark()))
    return executor, vault, vault.create_chat()


def label_of(vault, chat, value):
    return next(k for k, v in vault.mapping(chat).items() if v == value)


def raw(result) -> str:
    return json.dumps(result, ensure_ascii=False)


def test_contacts_come_back_masked_and_are_trusted_recipients(ex):
    executor, vault, chat = ex
    a = executor.propose(chat, "search_contacts", {"query": "Rahul"})
    assert a.status == "done" and "Rahul" not in raw(a.result) and "brightpath.in" not in raw(a.result)
    assert a.result["contacts"][0]["card"].startswith("<PERSON_1> <<CONTACT_1>>")
    send = executor.propose(chat, "send_email", {"to": [label_of(vault, chat, "Rahul Mehta")], "subject": "Hi", "body": "Hi"})
    assert send.status == "pending" and send.preview["to"] == ["rahul.mehta@brightpath.in"]


def test_your_contacts_vouch_for_an_address_first_seen_in_the_inbox(ex):
    executor, vault, chat = ex
    executor.propose(chat, "read_inbox", {})
    rahul = label_of(vault, chat, "Rahul Mehta")
    assert vault.from_tool(chat, label_of(vault, chat, "rahul.mehta@brightpath.in"))
    executor.propose(chat, "search_contacts", {"query": "Rahul"})
    assert executor.propose(chat, "send_email", {"to": [rahul], "subject": "Re", "body": "Paid"}).status == "pending"


def test_calendar_lists_masked_and_reschedules_after_confirm(ex):
    executor, vault, chat = ex
    a = executor.propose(chat, "list_events", {"query": "Banyan"})
    ev = a.result["events"][0]
    assert "Ananya" not in raw(a.result) and "<PERSON_1>" in ev["event"] and ev["start"].startswith("2026-11-05")
    move = executor.propose(chat, "reschedule_event", {"event_id": ev["id"], "start": "2026-11-06T15:00:00+05:30"})
    assert move.status == "pending"
    executor.confirm(move.action_id)
    again = executor.propose(chat, "list_events", {"query": "Banyan"})
    assert again.result["events"][0]["start"] == "2026-11-06T15:00:00+05:30"


def test_files_have_opaque_ids_and_a_planted_address_cant_be_mailed(ex):
    executor, vault, chat = ex
    found = executor.propose(chat, "search_files", {})
    assert len(found.result["files"]) == 7  # 3 documents, 3 tables, 1 PDF across the subfolders
    assert all(re.fullmatch(r"[0-9a-f]{10}", f["id"]) for f in found.result["files"])  # no names hidden in ids
    vendor = next(f for f in found.result["files"] if "vendor" in f["name"])
    doc = executor.propose(chat, "read_file", {"file_id": vendor["id"]})
    assert "doc-backup.co" not in raw(doc.result) and "<CONTACT_" in doc.result["text"]
    planted = label_of(vault, chat, "archive@doc-backup.co")
    send = executor.propose(chat, "send_email", {"to": [planted], "subject": "Files", "body": "Attached"})
    assert send.status == "refused" and "came from a tool result" in send.violations[0]


def test_bank_statement_masked_and_summed_on_device(ex):
    executor, vault, chat = ex
    a = executor.propose(chat, "read_transactions", {"query": "Swiggy"})
    rows = a.result["transactions"]
    assert len(rows) == 2 and "640" not in raw(a.result) and "<AMOUNT_" in rows[0]["entry"]
    first, second = (re.search(r"debit (<AMOUNT_\d+>)", r["entry"]).group(1) for r in rows)
    total = executor.propose(chat, "compute", {"expression": f"{first} + {second}"})
    assert total.status == "done" and total.result["result"] == "<RESULT_1>"
    assert vault.mapping(chat)["<RESULT_1>"] == "₹1,760"
    yes = executor.propose(chat, "compute", {"expression": f"{first} < {second}"})
    assert yes.result["result"] == "yes"


def test_compute_units_and_refusals(ex):
    executor, vault, chat = ex
    salary, _ = vault.entity_placeholder(chat, "AMOUNT", "₹24 lakh", base="SALARY")
    rent, _ = vault.entity_placeholder(chat, "AMOUNT", "₹38,000", base="RENT")
    pct = executor.propose(chat, "compute", {"expression": f"{rent} * 12 / {salary} * 100", "unit": "percent"})
    assert vault.mapping(chat)[pct.result["result"]] == "19%"
    person, _ = vault.entity_placeholder(chat, "PERSON", "Asha Rao")
    assert executor.propose(chat, "compute", {"expression": f"{person} * 2"}).status == "failed"
    assert executor.propose(chat, "compute", {"expression": "__import__('os').system('ls')"}).status == "failed"
    secret, _ = vault.entity_placeholder(chat, "SECRET", "hunter22")
    assert executor.propose(chat, "compute", {"expression": f"{secret} + 1"}).status == "refused"
    assert evaluate(to_python("$1.5m - $200k")[0]) == 1_300_000


def test_chat_channels_read_masked_and_shared_channels_get_no_hidden_values(ex):
    executor, vault, chat = ex
    fin = executor.propose(chat, "read_channel", {"channel": "#finance"})
    assert "Ananya" not in raw(fin.result) and "2,40,000" not in raw(fin.result) and fin.result["channel"] == "#finance"
    amount = re.search(r"<AMOUNT_\d+>", fin.result["messages"][0]["message"]).group(0)
    leak = executor.propose(chat, "post_message", {"channel": "#partners-shared", "text": f"Invoice is {amount}"})
    assert leak.status == "refused" and "shared with people outside" in leak.violations[0]
    assert executor.propose(chat, "post_message", {"channel": "#partners-shared", "text": "We'll get back to you."}).status == "pending"
    assert executor.propose(chat, "post_message", {"channel": "#finance", "text": f"Paying {amount} Friday"}).status == "pending"
    assert executor.propose(chat, "post_message", {"channel": "#leaks", "text": "hi"}).status == "refused"


def test_health_records_masked(ex):
    executor, _, chat = ex
    a = executor.propose(chat, "read_health_records", {})
    assert [r["date"] for r in a.result["reports"]] == ["2026-10-20", "2026-09-02"]
    assert "Sunita" not in raw(a.result) and "Kavita" not in raw(a.result) and "<PERSON_" in a.result["reports"][0]["report"]


def test_your_own_data_folder_replaces_the_samples(ex, tmp_path, monkeypatch):
    executor, _, chat = ex
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "contacts.vcf").write_text("BEGIN:VCARD\nFN:Asha Rao\nEMAIL:asha@example.in\nEND:VCARD\n")
    monkeypatch.setenv("MUSE_SHIELD_DATA_DIR", str(tmp_path / "data"))
    a = executor.propose(chat, "search_contacts", {})
    assert a.result["status"] == "1 of 1 contacts" and "asha@" not in raw(a.result)


def test_channel_names_are_never_masked(tmp_path, monkeypatch):
    """Tool descriptions list your channels, so masking one would only make the pre-send guard refuse the chat."""
    from muse_shield.connectors.personal import channel_names

    monkeypatch.delenv("MUSE_SHIELD_DATA_DIR", raising=False)
    NAMES["#partners-shared"] = "ORG"
    try:
        vault = Vault(tmp_path / "v.db", b"\x71" * 32)
        chat = vault.create_chat()
        assert Masker(vault, lookup_spark()).mask("Read #partners-shared now.", chat).masked_text == "Read <ORG_1> now."
        masked = Masker(vault, lookup_spark(), public=channel_names).mask("Read #partners-shared now.", chat)
        assert masked.masked_text == "Read #partners-shared now." and masked.spans == []
    finally:
        del NAMES["#partners-shared"]


@pytest.mark.parametrize("expr, want", [
    ("₹38,000 / ₹1,60,000 a month * 100", 23.75),       # seen live: the masked salary carried 'a month'
    ("(₹38,000 / ₹1,60,000 per month) * 100", 23.75),
    ("₹1,60,000/month * 12", 1_920_000),
    ("₹4.2 lakh p.a. - ₹50,000", 370_000),
    ("₹24 LPA / 12", 200_000),
    ("max(₹2,40,000, ₹38 lakh)", 3_800_000),             # the comma between arguments isn't part of a number
    ("₹1,60,000 take-home - ₹38,000", 122_000),         # a hyphenated word must not leave a minus behind
    ("round(₹1,234.567, 2)", 1234.57),                   # whole numbers stay ints
])
def test_compute_reads_amounts_as_the_analysis_marked_them(expr, want):
    assert evaluate(to_python(expr)[0]) == pytest.approx(want)
