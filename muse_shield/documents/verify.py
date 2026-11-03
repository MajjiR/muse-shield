"""The safety net: re-open a masked copy and look everywhere for every value that was masked.

A copy is only offered for download if this passes. Failures say where (a part, a page) and which
placeholder, never the value itself.
"""

from __future__ import annotations

import io
import re
import unicodedata
import urllib.parse
import zipfile
from dataclasses import dataclass, field

from ..app.chat import find_leaks
from .text import build, flat

MIN_RAW = 5        # shortest value searched for in raw XML or PDF streams (shorter ones match by accident)
MIN_SPACELESS = 6  # shortest value also searched with spaces and hyphens removed ("Mal- hotra", "4111 1111…")
FORBIDDEN_PARTS = ("media/", "embeddings/", "customxml/", "docprops/", "thumbnail", "comments", "vbaproject",
                   "fonts/", "charts/", "diagrams/", "tags/", "printersettings", "people.xml", "authors.xml")
PDF_ACTIONS = (b"/JavaScript", b"/JS ", b"/JS(", b"/JS<", b"/EmbeddedFile", b"/Launch", b"/SubmitForm", b"/ImportData")


@dataclass
class VerifyReport:
    ok: bool = True
    checks: int = 0
    failures: list[dict] = field(default_factory=list)   # {"label", "where"}
    warnings: list[dict] = field(default_factory=list)   # {"code", ...}

    def fail(self, label: str, where: str) -> None:
        self.ok = False
        if {"label": label, "where": where} not in self.failures:
            self.failures.append({"label": label, "where": where})

    def to_dict(self) -> dict:
        return {"ok": self.ok, "checks": self.checks, "failures": self.failures, "warnings": self.warnings}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("­", "").replace(" ", " ")
    return re.sub(r"\s+", " ", text).casefold()


def _spaceless(text: str) -> str:
    return re.sub(r"[\s\-‐-―]+", "", norm(text))


class _Needles:
    def __init__(self, secrets: list[tuple[str, str]]):
        self.items = []
        for label, value in secrets:
            n = norm(value).strip()
            if len(n) < 3:
                continue
            word = re.compile(rf"(?<!\w){re.escape(n)}(?!\w)")
            self.items.append((label, n, word, _spaceless(value) if len(_spaceless(value)) >= MIN_SPACELESS else None,
                               value.strip()))

    def scan_text(self, text: str, where: str, report: VerifyReport) -> None:
        n, sl = norm(text), _spaceless(text)
        for label, value, word, spaceless, _ in self.items:
            report.checks += 1
            if word.search(n) or (spaceless and spaceless in sl):
                report.fail(label, where)

    def scan_raw(self, data: bytes, where: str, report: VerifyReport) -> None:
        low = data.lower()
        for label, value, _, _, raw in self.items:
            if len(value) < MIN_RAW:
                continue
            report.checks += 1
            forms = set()
            for v in {raw, value}:  # as written and casefolded; hex compares case-insensitively below
                forms |= {v.encode("utf-8"), v.encode("utf-16-be"), v.encode("utf-8").hex().encode(),
                          v.encode("utf-16-be").hex().encode(), v.replace("&", "&amp;").encode("utf-8")}
                try:
                    forms.add(v.encode("latin-1"))
                except UnicodeEncodeError:
                    pass
            if any(f.lower() in low for f in forms):
                report.fail(label, where)


def verify(md, filename: str | None = None) -> VerifyReport:
    """Check a pipeline.MaskedDocument's copy. `filename` (the original name) is checked too."""
    secrets = md.secret_labels()
    if filename:
        stem = filename.rsplit(".", 1)[0]
        if len(stem) >= 6:
            secrets.append(("file name", stem))
    report = VerifyReport()
    needles = _Needles(secrets)
    if md.missed:
        report.fail(f"{md.missed} masked value(s)", "not written into the copy")
    if md.format == "pdf":
        _verify_pdf(md, needles, report)
    else:
        _verify_ooxml(md, needles, report)
    conflicts = find_leaks(md.masked.masked_text, {label: v for label, v in secrets if label.startswith("<")})
    if conflicts:  # the chat's pre-send guard would refuse this text later (a short value inside another word)
        report.warnings.append({"code": "guard_conflict", "labels": sorted(set(conflicts))})
    return report


def _verify_ooxml(md, needles: _Needles, report: VerifyReport) -> None:
    from lxml import etree

    from .ooxml import CT_NS, R_NS, Package
    from .pipeline import handler

    z = zipfile.ZipFile(io.BytesIO(md.data))
    names = z.namelist()
    for name in names:
        low = name.lower()
        if any(f in low for f in FORBIDDEN_PARTS) or not low.endswith((".xml", ".rels")):
            report.fail("leftover part", name)
    pkg = Package(md.data)
    # Structure: every relationship id used in a part exists, every internal target exists, every part has a type.
    ct = pkg.xml("[Content_Types].xml")
    overrides = {o.get("PartName", "").lstrip("/").lower() for o in ct.iterfind(f"{{{CT_NS}}}Override")}
    defaults = {d.get("Extension", "").lower() for d in ct.iterfind(f"{{{CT_NS}}}Default")}
    for name in names:
        if name != "[Content_Types].xml" and name.lower() not in overrides and name.rsplit(".", 1)[-1].lower() not in defaults:
            report.fail("missing content type", name)
        if name.endswith(".rels") or name == "[Content_Types].xml" or not name.lower().endswith(".xml"):
            continue
        ids = pkg.rel_ids(name)
        for el in pkg.xml(name).iter():
            for attr, val in el.attrib.items():
                if attr.startswith(f"{{{R_NS}}}") and val and val not in ids:
                    report.fail("broken relationship", name)
        for rel in pkg.rels(name):
            t = pkg.target(name, rel)
            if t and not pkg.has(t):
                report.fail("broken relationship", name)
    # Every value, in every channel of every part.
    for name in names:
        data = z.read(name)
        report.checks += 1
        needles.scan_raw(data, name, report)
        if not name.lower().endswith((".xml", ".rels")):
            continue
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
        needles.scan_text(" ".join(t for t in root.itertext()), name, report)
        needles.scan_text("".join(t for t in root.itertext()), name, report)  # runs split mid-word
        attrs = " ".join(urllib.parse.unquote(v) for el in root.iter() for v in el.attrib.values())
        needles.scan_text(attrs, name, report)
    # The copy must read back as exactly the masked text.
    h = handler(md.format)
    again = build(h.blocks(Package(md.data))).text
    report.checks += 1
    if flat(again) != flat(md.expected_text):
        report.fail("text differs from the masked text", "whole document")
    try:
        if md.format == "docx":
            import docx
            docx.Document(io.BytesIO(md.data))
        else:
            import pptx
            prs = pptx.Presentation(io.BytesIO(md.data))
            for slide in prs.slides:
                _ = [s for s in slide.shapes]
    except Exception:
        report.fail("does not open", "whole document")


def _verify_pdf(md, needles: _Needles, report: VerifyReport) -> None:
    import pymupdf

    from .pdf import FLAGS

    doc = pymupdf.open(stream=md.data, filetype="pdf")
    labels = re.findall(r"<[A-Z][A-Z_]*_\d+>", md.expected_text)
    out_text = []
    for page in doc:
        where = f"page {page.number + 1}"
        text = page.get_text("text", flags=FLAGS)
        out_text.append(text)
        needles.scan_text(text, where, report)
        if list(page.annots()) or list(page.widgets()) or page.get_links():
            report.fail("annotations, form fields or links", where)
        if page.get_images():
            report.fail("image left", where)
    md_vals = doc.metadata or {}
    if any(md_vals.get(k) for k in ("author", "title", "subject", "keywords", "creator", "producer")):
        report.fail("document properties", "metadata")
    if doc.get_xml_metadata() or doc.get_toc() or doc.embfile_count() or doc.is_form_pdf:
        report.fail("metadata, bookmarks, attachments or form", "document")
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=False).encode("latin-1", "replace")
            stream = doc.xref_stream(xref) if doc.xref_is_stream(xref) else b""
        except Exception:
            continue
        for blob in (obj, stream or b""):
            needles.scan_raw(blob, f"object {xref}", report)
        if any(a in obj for a in PDF_ACTIONS):
            report.fail("script, attachment or action", f"object {xref}")
    # Every placeholder should be readable in the copy; text that vanished outside spans is collateral.
    joined = "\n".join(out_text)
    missing = sum(1 for lab in set(labels) if lab not in joined)
    if missing:
        report.warnings.append({"code": "labels_unreadable", "count": missing})
    expected_words = set(re.findall(r"\w{3,}", re.sub(r"<[A-Z][A-Z_]*_\d+>|\[[A-Z_]+\]", " ", md.expected_text)))
    got = set(re.findall(r"\w{3,}", joined))
    lost = sorted(expected_words - got)
    if lost:
        report.warnings.append({"code": "collateral", "count": len(lost)})
