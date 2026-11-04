"""PDF with a text layer: true redaction with PyMuPDF. The text under each box is removed from the
file, and the placeholder is written in its place as real, selectable text."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pymupdf

from . import DocumentError
from .text import Atom, Block, DocText

pymupdf.TOOLS.set_small_glyph_heights(True)  # character boxes that don't overlap the lines above and below

# No TEXT_MEDIABOX_CLIP: text placed off the page is still in the file, so it must be analysed too.
# No TEXT_PRESERVE_LIGATURES: "ﬁ" becomes "fi", so the analyzer reads normal words.
FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_ACCURATE_BBOXES
UNREADABLE = 0.2   # share of characters with no Unicode mapping above which a page counts as unreadable
LABEL_FONT = "helv"

# Pastel fills by placeholder type, matching the web app (bg, ink).
TONES = {"PERSON": ((0.925, 0.894, 0.984), (0.239, 0.165, 0.451)), "ORG": ((0.992, 0.906, 0.839), (0.42, 0.208, 0.063)),
         "AMOUNT": ((0.855, 0.953, 0.898), (0.114, 0.353, 0.227)), "ID": ((0.984, 0.882, 0.902), (0.431, 0.122, 0.192)),
         "CONTACT": ((0.867, 0.933, 0.984), (0.11, 0.29, 0.439)), "PLACE": ((0.965, 0.933, 0.859), (0.353, 0.271, 0.075)),
         "DATE": ((0.937, 0.89, 0.965), (0.333, 0.145, 0.431)), "CONTEXT": ((0.886, 0.925, 0.992), (0.122, 0.247, 0.478))}
_TYPE_TONE = {"PERSON": "PERSON", "ORG": "ORG", "ID": "ID", "SECRET": "ID", "SENSITIVE_ATTRIBUTE": "ID", "CONTACT": "CONTACT",
              "ADDRESS": "PLACE", "LOCATION": "PLACE", "DATE": "DATE"}


@dataclass
class Line:
    page: int
    chars: list[tuple[str, tuple, float, tuple]]   # (char, bbox, size, origin), one per character of the atom text
    dir: tuple[float, float]
    hyphen: tuple | None = None                      # bbox of a line-end hyphen dropped when joining "Mal-" + "hotra"


@dataclass
class PdfDoc:
    doc: pymupdf.Document
    page_status: list[dict] = field(default_factory=list)   # {"page", "status": "ok"|"scanned"|"unreadable"|"empty"}
    unchecked: set[int] = field(default_factory=set)
    label_types: dict[str, str] = field(default_factory=dict)   # label -> entity type or "CONTEXT", for fill colours
    unlabelled: int = 0   # boxes on slanted text, filled without a label


def load(data: bytes) -> PdfDoc:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise DocumentError("unreadable", "the PDF is damaged") from None
    if doc.needs_pass or doc.is_encrypted:
        raise DocumentError("unsupported", "password-protected PDFs aren't supported; remove the password first", 415)
    return PdfDoc(doc)


def pages(pd: PdfDoc) -> int:
    return pd.doc.page_count


def metadata(pd: PdfDoc) -> list[str]:
    md = pd.doc.metadata or {}
    return [v.strip() for k in ("author", "title", "subject", "keywords") if (v := md.get(k)) and len(v.strip()) >= 3]


def sanitize(pd: PdfDoc) -> list[dict]:
    doc, n = pd.doc, Counter()
    where: dict[str, list[int]] = {}
    if doc.is_repaired:
        n["repaired"] += 1
    ocgs = doc.get_ocgs()
    if ocgs:  # hidden layers would hide text from extraction but keep it in the file: show them all
        doc.set_layer(-1, on=list(ocgs))
        n["layers_shown"] += len(ocgs)
    n["bookmarks_removed"] += len(doc.get_toc())
    doc.set_toc([])
    n["attachments_removed"] += doc.embfile_count()
    for name in doc.embfile_names():
        doc.embfile_del(name)
    doc.set_metadata({})
    doc.del_xml_metadata()
    pd.page_status = []
    for page in doc:
        page.remove_rotation()
        # Text drawn outside the visible page isn't extracted, so it can't be analysed: remove it.
        outside = [pymupdf.Rect(b) for kind, b in page.get_bboxlog() if "text" in kind and not pymupdf.Rect(b) in page.rect]
        if outside:
            for r in outside:
                page.add_redact_annot(r, cross_out=False)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            n["offpage_text_removed"] += len(outside)
            where.setdefault("offpage_text_removed", []).append(page.number + 1)
        pd.page_status.append(_status(page))
        if pd.page_status[-1]["status"] not in ("ok", "empty"):
            pd.unchecked.add(page.number)
        for annot in list(page.annots() or []):
            n["annotations_removed"] += 1
            page.delete_annot(annot)
        for widget in list(page.widgets() or []):
            n["form_fields_removed"] += 1
            page.delete_widget(widget)
        for link in page.get_links():
            n["links_removed"] += 1
            page.delete_link(link)
        images = [i for i in page.get_image_info(xrefs=True) if pymupdf.Rect(i["bbox"]).is_valid]
        if images:
            for img in images:
                page.add_redact_annot(pymupdf.Rect(img["bbox"]) & page.rect or page.rect, cross_out=False)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                  text=pymupdf.PDF_REDACT_TEXT_NONE)
            n["images_removed"] += len(images)
            where.setdefault("images_removed", []).append(page.number + 1)
    out = [{"code": c, "count": k, **({"where": [f"page {p}" for p in sorted(set(where[c]))]} if c in where else {})}
           for c, k in n.items() if k]
    return out


def _lines(page: pymupdf.Page) -> list[list[Line | str]]:
    """Text blocks on a page, each a list of Lines."""
    out = []
    for block in page.get_text("rawdict", flags=FLAGS)["blocks"]:
        if block.get("type") != 0:
            continue
        lines = []
        for line in block["lines"]:
            chars = [(ch["c"], tuple(ch["bbox"]), span["size"], tuple(ch["origin"]))
                     for span in line["spans"] for ch in span["chars"]]
            if any(c.strip() for c, *_ in chars):
                lines.append(Line(page.number, chars, tuple(round(d, 3) for d in line["dir"])))
        if lines:
            out.append(lines)
    return out


def _status(page: pymupdf.Page) -> dict:
    """ok, empty, scanned (images but no text) or unreadable (text with no Unicode mapping)."""
    chars = [c for b in _lines(page) for line in b for c, *_ in line.chars]
    if not chars:
        status = "scanned" if page.get_images() or page.get_image_info() else ("empty" if not page.get_drawings() else "no_text")
    elif sum(1 for c in chars if c == "\ufffd" or 0xE000 <= ord(c) <= 0xF8FF) / len(chars) > UNREADABLE:
        status = "unreadable"
    else:
        status = "ok"
    return {"page": page.number + 1, "status": status}


def blocks(pd: PdfDoc) -> list[Block]:
    out: list[Block] = []
    for page in pd.doc:
        if page.number in pd.unchecked:
            continue
        page_blocks = _lines(page)
        for lines in page_blocks:
            atoms: list[Atom] = []
            for i, line in enumerate(lines):
                text = "".join(c for c, *_ in line.chars)
                nxt = lines[i + 1] if i + 1 < len(lines) else None
                joined = False
                if nxt and text.rstrip().endswith("-") and "".join(c for c, *_ in nxt.chars).lstrip()[:1].islower():
                    k = len(text.rstrip()) - 1  # drop the hyphen: "Mal-" + "hotra" reads "Malhotra"
                    line.hyphen = line.chars[k][1]
                    line.chars = line.chars[:k]
                    text = text[:k]
                    joined = True
                atoms.append(Atom(text, line, "text"))
                if nxt and not joined:
                    atoms.append(Atom(" ", kind="synthetic"))
            out.append(Block(atoms, f"page {page.number + 1}"))
    return out


def _tone(label: str | None, types: dict[str, str]):
    t = types.get(label or "", "")
    return TONES.get(_TYPE_TONE.get(t, t), TONES["CONTEXT"])


ROTATE = {(1.0, 0.0): 0, (0.0, -1.0): 90, (-1.0, 0.0): 180, (0.0, 1.0): 270}  # text direction -> insert_text rotate


def _rect(boxes: list[tuple], direction: tuple[float, float]) -> pymupdf.Rect:
    r = pymupdf.Rect(boxes[0])
    for b in boxes[1:]:
        r |= pymupdf.Rect(b)
    # Redaction removes every character whose box touches the rectangle: keep clear of the lines either side
    # (across the line) and of the neighbouring letters (along it).
    if abs(direction[0]) >= abs(direction[1]):
        return pymupdf.Rect(r.x0 + 0.2, r.y0 + 0.15 * r.height, r.x1 - 0.2, r.y1 - 0.15 * r.height)
    return pymupdf.Rect(r.x0 + 0.15 * r.width, r.y0 + 0.2, r.x1 - 0.15 * r.width, r.y1 - 0.2)


def apply(pd: PdfDoc, dt: DocText, replacements: list[tuple[int, int, str]]) -> int:
    doc = pd.doc
    todo: dict[int, list[tuple[pymupdf.Rect, str, bool, float, tuple, tuple]]] = {}  # rect, label, first piece, …
    missed = 0
    for start, end, label in replacements:
        pieces = [(a, lo, hi) for a, lo, hi in dt.locate(start, end) if a.kind == "text"]
        if not pieces:
            missed += 1
            continue
        for i, (atom, lo, hi) in enumerate(pieces):
            line: Line = atom.ref
            boxes = [b for _, b, _, _ in line.chars[lo:hi]]
            if line.hyphen and hi == len(atom.text) and i + 1 < len(pieces):
                boxes.append(line.hyphen)
            if not boxes:
                continue
            size, origin = line.chars[lo][2], line.chars[lo][3]
            todo.setdefault(line.page, []).append((_rect(boxes, line.dir), label, i == 0, size, origin, line.dir))
    for pno, items in todo.items():
        page = doc[pno]
        for rect, label, *_ in items:  # every piece of a value in its type's colour
            page.add_redact_annot(rect, fill=_tone(label, pd.label_types)[0], cross_out=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        for rect, label, first, size, origin, direction in items:  # after apply_redactions, which would erase them
            if not first:  # a value wrapped onto the next line is labelled once
                continue
            if direction not in ROTATE:
                pd.unlabelled += 1
                continue
            width = pymupdf.get_text_length(label, LABEL_FONT, 1)
            room = rect.width if ROTATE[direction] in (0, 180) else rect.height
            fs = max(5.0, min(size, room / width * 0.95 if width else size))  # a short name gets a small label
            page.insert_text(origin, label, fontname=LABEL_FONT, fontsize=fs, rotate=ROTATE[direction],
                             color=_tone(label, pd.label_types)[1])
    for pno in sorted(pd.unchecked):  # no text layer: we can't tell what's on it, so nothing of it is kept
        page = doc[pno]
        page.add_redact_annot(page.rect, fill=(1, 1, 1), cross_out=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        page.insert_text((48, 72), f"Page {pno + 1} not checked: content removed (no readable text layer).",
                         fontname=LABEL_FONT, fontsize=11, color=(0.3, 0.3, 0.3))
    return missed


def save(pd: PdfDoc) -> bytes:
    doc = pd.doc
    doc.scrub(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=False, javascript=True,
              metadata=True, redactions=False, remove_links=True, reset_fields=True, reset_responses=True,
              thumbnails=True, xml_metadata=True)
    doc.set_metadata({})
    cat = doc.pdf_catalog()
    for key in ("Names", "PageMode", "OpenAction", "AA", "AcroForm", "Outlines", "PageLabels", "Metadata"):
        doc.xref_set_key(cat, key, "null")  # leftovers like an empty attachment list, or "open on attachments"
    return doc.tobytes(garbage=4, deflate=True, clean=True)
