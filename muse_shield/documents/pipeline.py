"""Mask one document end to end: sniff, sanitize, extract, mask, write back."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from importlib import import_module

from ..app.engine import Masked, Masker
from . import MAX_CHARS, MAX_PAGES, DocumentError, sniff
from .text import MAX_UNIT_CHARS, DocText, build


def handler(fmt: str):
    return import_module(f".{fmt}", __package__)


@dataclass
class MaskedDocument:
    format: str
    data: bytes                     # the masked copy, in the same format
    doc_text: DocText
    masked: Masked
    pages: int
    warnings: list[dict] = field(default_factory=list)
    page_status: list[dict] = field(default_factory=list)
    metadata: list[str] = field(default_factory=list)   # original property values (author, company…) for the verifier
    missed: int = 0                 # replacements the writer couldn't place (the verifier refuses these files)
    seconds: float = 0.0
    replacements: list[tuple[int, int, str]] = field(default_factory=list)

    @property
    def expected_text(self) -> str:
        """What the masked copy should read: the masked text, plus [TYPE] for values the chat already saw."""
        text, out, cur = self.doc_text.text, [], 0
        for s, e, label in self.replacements:
            out += [text[cur:s], label]
            cur = e
        return "".join(out + [text[cur:]])

    def secret_labels(self) -> list[tuple[str, str]]:
        """(where it came from, value) for everything that must not appear in the copy. Reports name the first."""
        out = [(s["placeholder"], s["text"]) for s in self.masked.spans if s["kind"] == "entity"]
        out += [(f"[{a['type']}]", a["text"]) for a in self.masked.already_sent]
        out += [("document properties", v) for v in self.metadata]
        for c in self.masked.contexts:  # a passage leaks if any of its longer sentences survives
            out += [(c["label"], sent) for sent in re.split(r"(?<=[.!?])\s+", self.masked.original[c["start"]:c["end"]])
                    if len(sent.strip()) >= 20]
        return [(k, v.strip()) for k, v in out if v and v.strip()]


def mask_document(data: bytes, masker: Masker, chat_id: str, *, max_unit_chars: int = MAX_UNIT_CHARS,
                  on_progress=None) -> MaskedDocument:
    t0 = time.perf_counter()
    fmt = sniff(data)
    h = handler(fmt)
    doc = h.load(data)
    pages = h.pages(doc)
    if pages > MAX_PAGES:
        raise DocumentError("too_large", f"up to {MAX_PAGES} pages or slides", 413)
    metadata = h.metadata(doc)
    warnings = h.sanitize(doc)
    dt = build(h.blocks(doc), max_unit_chars)
    if len(dt.text) > MAX_CHARS:
        raise DocumentError("too_large", f"up to {MAX_CHARS:,} characters of text", 413)
    masked = masker.mask(dt.text, chat_id, propagate=True, on_progress=on_progress, title=False)
    if not masked.analysis_ok:
        raise DocumentError("analysis_failed", masked.error, 502)
    # Values the model already saw in this chat stay readable in the chat, but not in a file someone may share.
    extra = [(a["start"], a["end"], f"[{a['type']}]") for a in masked.already_sent]
    reps = sorted(masked.replacements() + extra)
    if hasattr(doc, "label_types"):
        doc.label_types = {s["placeholder"]: ("CONTEXT" if s["kind"] == "context" else s["type"]) for s in masked.spans}
        doc.label_types.update({f"[{a['type']}]": a["type"] for a in masked.already_sent})
    missed = h.apply(doc, dt, reps)
    out = h.save(doc)
    return MaskedDocument(fmt, out, dt, masked, pages, warnings, getattr(doc, "page_status", []), metadata, missed,
                          time.perf_counter() - t0, reps)
