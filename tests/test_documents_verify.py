"""The verifier must catch a leak in every place a value can hide. Each test plants one into a clean copy."""

import io
import zipfile

import pymupdf
import pytest
from doc_fakes import fake_values
from doc_fixtures import TRICKY_DOCX_VALUES, TRICKY_PDF_VALUES, TRICKY_PPTX_VALUES, png, tricky_docx, tricky_pdf, tricky_pptx

from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.documents.pipeline import mask_document
from muse_shield.documents.verify import verify


def _masked(make, values):
    vault = Vault(":memory:", b"\x77" * 32)
    return mask_document(make(), Masker(vault, fake_values(values)), vault.create_chat())


@pytest.fixture
def docx_md():
    return _masked(tricky_docx, TRICKY_DOCX_VALUES)


def _edit_zip(data: bytes, edit) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    files = {n: src.read(n) for n in src.namelist()}
    edit(files)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


def test_clean_copies_pass():
    for make, values in ((tricky_docx, TRICKY_DOCX_VALUES), (tricky_pptx, TRICKY_PPTX_VALUES), (tricky_pdf, TRICKY_PDF_VALUES)):
        report = verify(_masked(make, values), "Arjun_Malhotra_offer")
        assert report.ok, report.failures


@pytest.mark.parametrize("plant, where", [
    (lambda f: f.__setitem__("word/document.xml", f["word/document.xml"].replace(b"&lt;ORG_1&gt;", b"Kestrel Labs", 1)), "word/document.xml"),
    (lambda f: f.__setitem__("word/document.xml", f["word/document.xml"].replace(b"&lt;ORG_1&gt;", b"Kestrel</w:t></w:r><w:r><w:t> Labs", 1)), "word/document.xml"),
    (lambda f: f.__setitem__("word/_rels/document.xml.rels", f["word/_rels/document.xml.rels"].replace(
        b"</Relationships>", b'<Relationship Id="rX" Type="x/hyperlink" Target="mailto:arjun.m%40example.com" TargetMode="External"/></Relationships>')),
     "word/_rels/document.xml.rels"),
    (lambda f: f.__setitem__("word/styles.xml", f["word/styles.xml"].replace(b"<w:styles ", b'<w:styles w:x="Meera Pillai" ', 1)), "word/styles.xml"),
    (lambda f: f.__setitem__("word/media/image1.png", png().getvalue()), "word/media/image1.png"),
    (lambda f: f.__setitem__("docProps/core.xml", b"<cp:coreProperties xmlns:cp='x'><creator>Meera Pillai</creator></cp:coreProperties>"), "docProps/core.xml"),
])
def test_planted_ooxml_leaks_are_caught(docx_md, plant, where):
    docx_md.data = _edit_zip(docx_md.data, plant)
    report = verify(docx_md)
    assert not report.ok
    assert where in {f["where"] for f in report.failures}
    assert not any(v in str(report.to_dict()) for v in TRICKY_DOCX_VALUES)  # reports never repeat a value


def test_a_value_the_writer_missed_is_caught(docx_md):
    docx_md.missed = 1
    assert not verify(docx_md).ok


def test_filename_is_checked(docx_md):
    docx_md.data = _edit_zip(docx_md.data, lambda f: f.__setitem__(
        "word/document.xml", f["word/document.xml"].replace(b"Please confirm", b"Re: Offer_2026_final_v3 Please confirm")))
    assert not verify(docx_md, "Offer_2026_final_v3.docx").ok


@pytest.fixture
def pdf_md():
    return _masked(tricky_pdf, TRICKY_PDF_VALUES)


def _edit_pdf(md, edit):
    doc = pymupdf.open(stream=md.data, filetype="pdf")
    edit(doc)
    md.data = doc.tobytes()


@pytest.mark.parametrize("plant", [
    lambda d: d[0].insert_text((72, 400), "Arjun Malhotra"),                         # visible text
    lambda d: d[0].insert_text((72, 2000), "BNZPV4567L"),                            # off the page
    lambda d: d.set_metadata({"author": "Meera Pillai"}),                            # properties
    lambda d: d[0].add_text_annot((50, 50), "note"),                                 # an annotation
    lambda d: d.embfile_add("x.txt", b"hello"),                                      # an attachment
    lambda d: d.update_stream(_new_stream(d), "Shreya Kulkarni".encode("utf-16-be")),  # raw, UTF-16
    lambda d: d[0].insert_image(pymupdf.Rect(0, 0, 50, 50), stream=png().getvalue()),  # an image
])
def test_planted_pdf_leaks_are_caught(pdf_md, plant):
    _edit_pdf(pdf_md, plant)
    assert not verify(pdf_md).ok


def _new_stream(doc):
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    return xref
