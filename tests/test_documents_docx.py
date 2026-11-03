import io
import zipfile

from doc_fakes import fake_values
from doc_fixtures import TRICKY_DOCX_VALUES, tricky_docx
from docx import Document

from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.documents import docx as D
from muse_shield.documents.ooxml import Package
from muse_shield.documents.pipeline import mask_document
from muse_shield.documents.text import build


def _run(tmp_path, data, values, **kw):
    vault = Vault(tmp_path / "v.db", b"\x55" * 32)
    return mask_document(data, Masker(vault, fake_values(values, **kw)), vault.create_chat())


def _everything(data: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(data))
    return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def test_tricky_docx_has_no_value_left_anywhere(tmp_path):
    r = _run(tmp_path, tricky_docx(), TRICKY_DOCX_VALUES)
    assert r.missed == 0
    everything = _everything(r.data)
    for value in [*TRICKY_DOCX_VALUES, "Ravi Kumar", "hr@kestrel.example", "Check with Arjun", "Photo of Arjun"]:
        assert value not in everything, value
    codes = {w["code"] for w in r.warnings}
    assert {"tracked_changes_accepted", "comments_removed", "links_removed", "fields_unlinked", "images_removed"} <= codes
    names = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert not [n for n in names if n.startswith(("word/media", "customXml", "docProps")) or "comments" in n]


def test_masked_copy_reads_back_as_the_masked_text(tmp_path):
    r = _run(tmp_path, tricky_docx(), TRICKY_DOCX_VALUES)
    again = build(D.blocks(Package(r.data))).text
    assert again == r.masked.masked_text
    assert "Dear <PERSON_1>, welcome to <ORG_1>." in again
    assert "Confidential: prepared for <PERSON_1>" in again  # header, same placeholder as the body


def test_label_keeps_first_run_formatting_and_file_opens(tmp_path):
    r = _run(tmp_path, tricky_docx(), TRICKY_DOCX_VALUES)
    doc = Document(io.BytesIO(r.data))
    runs = doc.paragraphs[0].runs
    label = next(x for x in runs if "<PERSON_1>" in x.text)
    assert label.bold
    assert doc.tables[0].cell(0, 1).text == "<AMOUNT_1>"

