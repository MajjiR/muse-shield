"""One text string per document, with a map from every character back to where it lives in the file.

Each format turns its text nodes into Atoms (a Word w:t, a PowerPoint a:t, a PDF line fragment) and
groups them into Blocks (a paragraph, a table row, a PDF text block). Blocks are packed into analysis
units: "\\n" between blocks inside a unit, "\\n\\n" between units, which is exactly how Masker's
paragraphs() splits text, so one unit is one Muse Spark call.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

MAX_UNIT_CHARS = 1500
XML_NS = "http://www.w3.org/XML/1998/namespace"


@dataclass(eq=False)
class Atom:
    text: str
    ref: object = None   # the writer's handle: an lxml text element, a separator element, or PDF character boxes
    kind: str = "text"   # "text": writable text node; "sep": an element that stands for one character
                         # (tab, break, hyphen) and is removed if a span covers it; "synthetic": added by us
    start: int = 0
    end: int = 0


@dataclass
class Block:
    atoms: list[Atom]
    where: str            # for people: "page 3", "slide 2 notes", "header"
    hard: bool = False    # starts a new part, slide or section: never packed with the block before it

    @property
    def text(self) -> str:
        return "".join(a.text for a in self.atoms)


@dataclass
class DocText:
    text: str
    atoms: list[Atom]
    units: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, where of its first block)
    _starts: list[int] = field(default_factory=list, repr=False)

    def locate(self, start: int, end: int) -> list[tuple[Atom, int, int]]:
        """The atoms covering text[start:end], each with the local [lo, hi) slice of its own text."""
        out = []
        i = max(bisect.bisect_right(self._starts, start) - 1, 0)
        while i < len(self.atoms) and self.atoms[i].start < end:
            a = self.atoms[i]
            lo, hi = max(start, a.start), min(end, a.end)
            if lo < hi:
                out.append((a, lo - a.start, hi - a.start))
            i += 1
        return out

    def where(self, offset: int) -> str:
        i = bisect.bisect_right([u[0] for u in self.units], offset) - 1
        return self.units[i][2] if i >= 0 else ""


_BLANK = re.compile(r"\n[ \t]*(?=\n)")


def build(blocks: list[Block], max_chars: int = MAX_UNIT_CHARS) -> DocText:
    """Pack blocks into units of up to max_chars (0: one block per unit) and lay out the text."""
    blocks = [b for b in blocks if b.text.strip()]
    for b in blocks:  # a blank line inside a block would split it into two analysis units
        prev_nl = False
        for a in b.atoms:
            if a.kind == "sep" and a.text == "\n":
                if prev_nl:
                    a.text = " "
                prev_nl = True
            elif a.text.strip():
                prev_nl = False

    units: list[list[Block]] = []
    size = 0
    for b in blocks:
        n = len(b.text)
        if not units or b.hard or max_chars <= 0 or size + 1 + n > max_chars:
            units.append([b])
            size = n
        else:
            units[-1].append(b)
            size += 1 + n

    atoms: list[Atom] = []
    spans: list[tuple[int, int, str]] = []
    pos = 0

    def add(a: Atom) -> None:
        nonlocal pos
        a.start, a.end = pos, pos + len(a.text)
        pos = a.end
        atoms.append(a)

    for ui, unit in enumerate(units):
        if ui:
            add(Atom("\n\n", kind="synthetic"))
        start = pos
        for bi, b in enumerate(unit):
            if bi:
                add(Atom("\n", kind="synthetic"))
            for a in b.atoms:
                add(a)
        spans.append((start, pos, unit[0].where))

    text = "".join(a.text for a in atoms)
    for s, e, _ in spans:
        if _BLANK.search(text, s, e):
            raise AssertionError("a blank line inside an analysis unit")
    return DocText(text, atoms, spans, [a.start for a in atoms])


def splice(dt: DocText, replacements: list[tuple[int, int, str]], set_text, remove) -> int:
    """Apply (start, end, label) replacements to the atoms behind them: the label goes into the first
    writable atom of each span (keeping that run's formatting), the rest of the span is emptied, and
    separator elements inside it are removed. set_text(atom, new_text) and remove(atom) do the writing.
    Returns how many replacements had no writable atom (the verifier will refuse those)."""
    cuts: dict[int, list[tuple[int, int, str]]] = {}
    by_id: dict[int, Atom] = {}
    missed = 0
    for start, end, label in replacements:
        pieces = dt.locate(start, end)
        placed = False
        for atom, lo, hi in pieces:
            if atom.kind == "sep":
                if lo == 0 and hi == len(atom.text):
                    remove(atom)
                continue
            if atom.kind != "text":
                continue
            by_id[id(atom)] = atom
            cuts.setdefault(id(atom), []).append((lo, hi, "" if placed else label))
            placed = True
        missed += not placed
    for key, cs in cuts.items():
        atom = by_id[key]
        out, cur = [], 0
        for lo, hi, new in sorted(cs):
            out += [atom.text[cur:lo], new]
            cur = hi
        out.append(atom.text[cur:])
        set_text(atom, "".join(out))
    return missed


def set_xml_text(atom: Atom, value: str) -> None:
    """set_text for OOXML text elements (w:t, a:t): keep spaces at the edges."""
    el = atom.ref
    el.text = value
    if el.tag.endswith("}t") and "wordprocessingml" in el.tag:
        el.set(f"{{{XML_NS}}}space", "preserve")


def remove_xml(atom: Atom) -> None:
    el = atom.ref
    if el.getparent() is not None:
        el.getparent().remove(el)


def flat(text: str) -> str:
    """Text with unit and block breaks collapsed, for comparing a re-extracted copy with the masked text."""
    return re.sub(r"\n+", "\n", text).strip()
