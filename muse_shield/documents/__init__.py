"""Document masking: PDF, Word (.docx) and PowerPoint (.pptx).

A document becomes one text string with a map back to every text node, is masked with the
same Masker as chat messages, then written back in its own format and verified: the masked
copy is only offered if no masked value is left anywhere in the file.
"""

from __future__ import annotations

import importlib.util
import io
import zipfile

MAX_BYTES = 25 * 1024 * 1024
MAX_PAGES = 300           # pages or slides
MAX_CHARS = 300_000       # extracted text
MAX_ZIP_MEMBERS = 2_000
MAX_UNZIPPED = 200 * 1024 * 1024

FORMATS = ("pdf", "docx", "pptx")

_MAIN_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml": "pptx",
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml": "pptx",
}


class DocumentError(ValueError):
    """A document we won't process. `code` is stable for clients; the message is for people."""

    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.status = code, status


def available() -> bool:
    """True when the optional `documents` extra (PyMuPDF, lxml, python-docx, python-pptx) is installed."""
    return all(importlib.util.find_spec(m) for m in ("pymupdf", "lxml"))


def sniff(data: bytes) -> str:
    """Return "pdf", "docx" or "pptx" from the bytes themselves (never the filename), or raise DocumentError."""
    if len(data) > MAX_BYTES:
        raise DocumentError("too_large", f"files up to {MAX_BYTES // (1024 * 1024)} MB", 413)
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise DocumentError("unsupported", "this is a password-protected Office file or a legacy .doc/.ppt; "
                                           "save it as an unprotected .docx or .pptx", 415)
    if data[:4] != b"PK\x03\x04":
        raise DocumentError("unsupported", "only PDF, .docx and .pptx files are supported", 415)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocumentError("unreadable", "the file is damaged") from None
    infos = z.infolist()
    names = [i.filename.lower() for i in infos]
    if len(infos) > MAX_ZIP_MEMBERS or sum(i.file_size for i in infos) > MAX_UNZIPPED:
        raise DocumentError("too_large", "the file unpacks to more than the size limit", 413)
    if len(set(names)) != len(names):
        raise DocumentError("unreadable", "the file has duplicate parts")
    if "[content_types].xml" not in names:
        raise DocumentError("unsupported", "only PDF, .docx and .pptx files are supported", 415)
    types = z.read(next(i for i in infos if i.filename.lower() == "[content_types].xml")).decode("utf-8", "replace")
    if "vbaProject" in types or "macroEnabled" in types:
        raise DocumentError("unsupported", "files with macros (.docm, .pptm) aren't supported", 415)
    if "purl.oclc.org/ooxml" in types or any("purl.oclc.org/ooxml" in z.read(i).decode("utf-8", "replace")[:600]
                                             for i in infos if i.filename.lower() in ("word/document.xml", "ppt/presentation.xml")):
        raise DocumentError("unsupported", "Strict Open XML isn't supported; save as a normal .docx or .pptx", 415)
    for ctype, fmt in _MAIN_TYPES.items():
        if ctype in types:
            return fmt
    raise DocumentError("unsupported", "only PDF, .docx and .pptx files are supported", 415)
