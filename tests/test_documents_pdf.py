import pymupdf
import pytest
from doc_fakes import fake_values
from doc_fixtures import TRICKY_PDF_VALUES, tricky_pdf

from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.documents import DocumentError
from muse_shield.documents.pipeline import mask_document


@pytest.fixture(scope="module")
def result():
    vault = Vault(":memory:", b"\x77" * 32)
    return mask_document(tricky_pdf(), Masker(vault, fake_values(TRICKY_PDF_VALUES)), vault.create_chat())


def _pages(data):
    return [p.get_text() for p in pymupdf.open(stream=data, filetype="pdf")]


def test_wrapped_and_hyphenated_names_are_found(result):
    assert "offer Arjun Malhotra the role" in result.doc_text.text
    assert "Ms. Shreya Kulkarni will" in result.doc_text.text
    assert "offer <PERSON_1> the role" in result.masked.masked_text and "Ms. <PERSON_2> will" in result.masked.masked_text


def test_text_under_boxes_is_gone_and_labels_are_selectable(result):
    pages = _pages(result.data)
    text = "\n".join(pages)
    for value in [*TRICKY_PDF_VALUES, "Arjun", "Malhotra", "Kul", "karni", "BNZPV"]:
        assert value not in text, value
    for label in ("<PERSON_1>", "<PERSON_2>", "<AMOUNT_1>", "<ID_1>", "<CONTACT_1>", "<PERSON_3>"):
        assert label in pages[0], label
    assert "the role of analyst." in pages[0] and "will be your manager." in pages[0]  # neighbours intact
    assert "<PERSON_1>" in pages[1]  # the page that was rotated


def test_annotations_links_attachments_metadata_and_images_are_removed(result):
    doc = pymupdf.open(stream=result.data, filetype="pdf")
    assert not any(doc.metadata.get(k) for k in ("author", "title", "subject", "keywords"))
    assert doc.get_toc() == [] and doc.embfile_count() == 0
    for page in doc:
        assert not list(page.annots()) and not page.get_links() and not page.get_images()
    codes = {w["code"] for w in result.warnings}
    assert {"annotations_removed", "links_removed", "attachments_removed", "bookmarks_removed", "images_removed"} <= codes


def test_scanned_page_is_not_checked_and_cleared(result):
    assert [s["status"] for s in result.page_status] == ["ok", "ok", "scanned"]
    assert _pages(result.data)[2].startswith("Page 3 not checked")


def test_encrypted_pdf_is_refused():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    vault = Vault(":memory:", b"\x77" * 32)
    with pytest.raises(DocumentError) as e:
        mask_document(data, Masker(vault, fake_values({})), vault.create_chat())
    assert e.value.status == 415
