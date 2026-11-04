"""Render the realistic examples (muse_shield.realistic) as Word, PowerPoint and PDF files.

The layouts are deliberately awkward for a masker: values split across runs, the first line in the
header, a "label: value" line as a table row, the last paragraph in speaker notes, and PDF text
wrapped in a narrow column so names break across lines. Everything is made up.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

UNICODE_FONT = next((p for p in ("/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Georgia.ttf")
                     if Path(p).exists()), None)  # has ₹ and accented letters (Arial Unicode predates ₹)


def _pieces(line: str, values: list[str]) -> list[tuple[str, bool]]:
    """Split a line into runs, cutting every value in the middle (the second half bold)."""
    cuts = set()
    for v in values:
        for m in re.finditer(re.escape(v), line):
            if len(v) > 3:
                cuts.add(m.start() + len(v) // 2)
    out, cur, bold = [], 0, False
    for c in sorted(cuts):
        out.append((line[cur:c], bold))
        cur, bold = c, not bold
    out.append((line[cur:], bold))
    return [p for p in out if p[0]]


def _paragraphs(text: str) -> list[str]:
    return [line for line in text.split("\n")]


def docx(text: str, values: list[str]) -> bytes:
    from docx import Document

    d = Document()
    lines = _paragraphs(text)
    first = next(i for i, line in enumerate(lines) if line.strip())
    d.sections[0].header.paragraphs[0].text = lines[first]
    table_done = False
    for line in lines[first + 1:]:
        m = re.match(r"^([^:]{2,30}):\s+(.+)$", line)
        if m and not table_done:
            row = d.add_table(rows=1, cols=2).rows[0]
            row.cells[0].text, row.cells[1].text = m.group(1), m.group(2)
            table_done = True
            continue
        p = d.add_paragraph()
        for piece, bold in _pieces(line, values):
            p.add_run(piece).bold = bold
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def pptx(text: str, values: list[str], per_slide: int = 6) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    lines = [line for line in _paragraphs(text) if line.strip()]
    title, body, notes = lines[0], lines[1:-1] or lines[1:], lines[-1] if len(lines) > 2 else ""
    for i in range(0, max(len(body), 1), per_slide):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = title if i == 0 else f"{title} (cont.)"
        tf = slide.shapes.add_textbox(Inches(0.6), Inches(1.6), Inches(8.8), Inches(5)).text_frame
        tf.word_wrap = True
        for k, line in enumerate(body[i:i + per_slide]):
            para = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
            for piece, bold in _pieces(line, values):
                run = para.add_run()
                run.text, run.font.bold, run.font.size = piece, bold, Pt(14)
    if notes:
        prs.slides[len(prs.slides) - 1].notes_slide.notes_text_frame.text = notes
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def pdf(text: str, width: float = 300, size: float = 11) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    font = pymupdf.Font(fontfile=UNICODE_FONT) if UNICODE_FONT else pymupdf.Font("helv")
    page, y = None, 0.0
    for para in _paragraphs(text):
        words, line = para.split(" "), ""
        rows = []
        for w in words:
            trial = f"{line} {w}".strip()
            if line and font.text_length(trial, size) > width:
                rows.append(line)
                line = w
            else:
                line = trial
        rows.append(line)
        for row in rows:
            if page is None or y > 780:
                page, y = doc.new_page(), 72
                if UNICODE_FONT:
                    page.insert_font(fontname="aru", fontfile=UNICODE_FONT)
            if row:
                page.insert_text((72, y), row, fontsize=size, fontname="aru" if UNICODE_FONT else "helv")
            y += size * 1.45
        y += size * 0.6
    doc.subset_fonts()  # embed only the glyphs used (the full Unicode font is 23 MB)
    return doc.tobytes(garbage=3, deflate=True)


def render(fmt: str, text: str, values: list[str]) -> bytes:
    return {"docx": lambda: docx(text, values), "pptx": lambda: pptx(text, values), "pdf": lambda: pdf(text)}[fmt]()
