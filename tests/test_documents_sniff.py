import io
import zipfile

import pymupdf
import pytest
from docx import Document
from pptx import Presentation

from muse_shield import documents
from muse_shield.documents import DocumentError, sniff


def _docx() -> bytes:
    buf = io.BytesIO()
    d = Document()
    d.add_paragraph("hello")
    d.save(buf)
    return buf.getvalue()


def _pptx() -> bytes:
    buf = io.BytesIO()
    Presentation().save(buf)
    return buf.getvalue()


def _pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    return doc.tobytes()


def test_sniffs_formats_from_bytes():
    assert (sniff(_docx()), sniff(_pptx()), sniff(_pdf())) == ("docx", "pptx", "pdf")
    assert documents.available()


def test_refuses_legacy_or_encrypted_office():
    with pytest.raises(DocumentError) as e:
        sniff(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 100)
    assert e.value.status == 415


def test_refuses_macro_enabled():
    src = zipfile.ZipFile(io.BytesIO(_docx()))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for i in src.infolist():
            data = src.read(i)
            if i.filename == "[Content_Types].xml":
                data = data.replace(b"wordprocessingml.document.main+xml", b"ms-word.document.macroEnabled.main+xml")
            out.writestr(i, data)
    with pytest.raises(DocumentError, match="macros"):
        sniff(buf.getvalue())


def test_refuses_other_files_and_size(monkeypatch):
    for data in (b"plain text", b"PK\x03\x04garbage"):
        with pytest.raises(DocumentError):
            sniff(data)
    monkeypatch.setattr(documents, "MAX_BYTES", 10)
    with pytest.raises(DocumentError) as e:
        sniff(_pdf())
    assert e.value.status == 413
