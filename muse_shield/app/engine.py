"""Call 1: Muse Spark analyzes each paragraph; the masker turns that into placeholders and context blocks.

    text --paragraphs--> Spark analyze() --> entity spans + context sentence ranges
         --> context blocks replace whole sentence runs (<DEAL_1>), keeping full/shape/summary in the vault
         --> remaining entities become <TYPE_n> / <ROLE_n>
         --> masked text, spans for the UI, edges for the graph, counts-only audit

If any paragraph's analysis fails, the whole message is reported unmasked-and-blocked
(analysis_ok=False) so nothing can be sent.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import combinations

from ..analysis import Analysis, split_sentences
from ..backends import Backend, BackendError
from ..costs import run_cost
from .vault import Vault

ALWAYS_MASK = {"PERSON", "ID", "CONTACT", "SECRET", "ADDRESS"}  # hard rules; the model can't keep these
_PARA = re.compile(r"(?:[^\n]|\n(?![ \t]*\n))+")
_NUMBER = re.compile(r"\d[\d,.]*")


def paragraphs(text: str) -> list[tuple[int, str]]:
    out = []
    for m in _PARA.finditer(text):
        chunk = m.group(0)
        lead = len(chunk) - len(chunk.lstrip())
        if chunk.strip():
            out.append((m.start() + lead, chunk.strip()))
    return out


def sentence_offsets(paragraph: str, sentences: list[str]) -> list[tuple[int, int]]:
    spans, cursor = [], 0
    for s in sentences:
        i = paragraph.find(s, cursor)
        if i < 0:
            i = cursor
        spans.append((i, i + len(s)))
        cursor = i + len(s)
    return spans


def placeholder_base(etype: str, role: str | None) -> str:
    if etype == "AMOUNT":
        return role if role and role != "OTHER" else "AMOUNT"
    return etype


@dataclass
class Masked:
    chat_id: str
    original: str
    masked_text: str
    spans: list[dict] = field(default_factory=list)
    contexts: list[dict] = field(default_factory=list)
    analysis_ok: bool = True
    error: str = ""
    latency_ms: float = 0.0
    cost_usd: float | None = None
    tokens: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"chat_id": self.chat_id, "masked_text": self.masked_text, "spans": self.spans, "contexts": self.contexts,
                "analysis_ok": self.analysis_ok, "error": self.error, "latency_ms": round(self.latency_ms, 1),
                "cost_usd": self.cost_usd}


class Masker:
    def __init__(self, vault: Vault, analyzer: Backend, workers: int = 4):
        self.vault, self.analyzer, self.workers = vault, analyzer, workers

    def _analyze(self, paras: list[tuple[int, str]]) -> list[Analysis]:
        if not paras:
            return []
        with ThreadPoolExecutor(max_workers=min(self.workers, len(paras))) as pool:
            return list(pool.map(lambda p: self.analyzer.analyze([p[1]])[0], paras))

    def mask(self, text: str, chat_id: str) -> Masked:
        t0 = time.perf_counter()
        paras = paragraphs(text)
        try:
            analyses = self._analyze(paras)
        except BackendError as exc:
            return Masked(chat_id, text, text, analysis_ok=False, error=f"analysis failed: {exc}",
                          latency_ms=(time.perf_counter() - t0) * 1000)
        bad = [a for a in analyses if not a.valid]
        tokens = {"in": 0, "out": 0, "cached_in": 0}
        for a in analyses:
            tokens["in"] += a.usage.get("prompt_tokens", 0)
            tokens["out"] += a.usage.get("completion_tokens", 0)
            tokens["cached_in"] += a.usage.get("prompt_tokens_details.cached_tokens", 0)
        elapsed = time.perf_counter() - t0
        cost = run_cost(getattr(self.analyzer, "model", ""), tokens, elapsed)["usd"]
        if bad:
            return Masked(chat_id, text, text, analysis_ok=False, error=f"analysis returned invalid output: {bad[0].error}",
                          latency_ms=elapsed * 1000, cost_usd=cost, tokens=tokens)

        entities: list[dict] = []
        blocks: list[dict] = []
        for (off, para), a in zip(paras, analyses):
            sentences = a.sentences or split_sentences(para) or [para]
            offs = sentence_offsets(para, sentences)
            for c in a.contexts:
                lo, hi = min(c.sentences), max(c.sentences)
                start, end = off + offs[lo - 1][0], off + offs[hi - 1][1]
                if any(start < b["end"] and b["start"] < end for b in blocks):
                    continue  # overlapping blocks: keep the first
                blocks.append({"start": start, "end": end, "kind": c.kind, "subtype": c.subtype, "summary": c.summary})
            for s in a.entities:
                entities.append({"start": off + s.start, "end": off + s.end, "text": s.text, "type": s.type, "role": s.role})

        # Longest entity wins on overlap.
        kept: list[dict] = []
        for e in sorted(entities, key=lambda e: e["end"] - e["start"], reverse=True):
            if not any(e["start"] < k["end"] and k["start"] < e["end"] for k in kept):
                kept.append(e)
        kept.sort(key=lambda e: e["start"])

        spans: list[dict] = []
        for e in kept:
            label, _ = self.vault.entity_placeholder(chat_id, e["type"], e["text"], placeholder_base(e["type"], e["role"]))
            spans.append({**e, "placeholder": label, "kind": "entity",
                          "source": "policy" if e["type"] in ALWAYS_MASK else "model"})

        contexts = []
        for b in sorted(blocks, key=lambda b: b["start"]):
            inner = [s for s in spans if b["start"] <= s["start"] and s["end"] <= b["end"]]
            block_text = text[b["start"]:b["end"]]
            shape, cursor = [], b["start"]
            for s in inner:
                shape += [_NUMBER.sub("[NUMBER]", text[cursor:s["start"]]), s["placeholder"]]
                cursor = s["end"]
            shape.append(_NUMBER.sub("[NUMBER]", text[cursor:b["end"]]))
            label = self.vault.add_context(chat_id, b["kind"], b["subtype"], block_text, "".join(shape), b["summary"])
            for s in inner:
                s["in_context"] = label
                self.vault.add_edge(chat_id, s["placeholder"], label, "mentioned_in")
            contexts.append({"label": label, "kind": b["kind"], "subtype": b["subtype"], "start": b["start"], "end": b["end"],
                             "summary": b["summary"]})

        # Build the masked text: context blocks first (they swallow their inner entities).
        pieces, cursor = [], 0
        replacements = [(c["start"], c["end"], c["label"]) for c in contexts]
        replacements += [(s["start"], s["end"], s["placeholder"]) for s in spans if not s.get("in_context")]
        for start, end, label in sorted(replacements):
            pieces += [text[cursor:start], label]
            cursor = end
        pieces.append(text[cursor:])
        masked_text = "".join(pieces)
        self.vault.title_from_masked(chat_id, masked_text)

        labels = sorted({s["placeholder"] for s in spans})
        for a_, b_ in combinations(labels[:25], 2):
            self.vault.add_edge(chat_id, a_, b_, "appears_with")
        counts: dict[str, int] = {}
        for s in spans:
            counts[s["type"]] = counts.get(s["type"], 0) + 1
        for c in contexts:
            counts[f"CONTEXT_{c['kind']}"] = counts.get(f"CONTEXT_{c['kind']}", 0) + 1
        self.vault.audit("mask", chat_id, counts)

        span_out = [{k: s.get(k) for k in ("start", "end", "text", "type", "role", "placeholder", "kind", "source")} | {"in_context": s.get("in_context")}
                    for s in spans]
        span_out += [{"start": c["start"], "end": c["end"], "text": text[c["start"]:c["end"]], "type": c["kind"], "role": None,
                      "placeholder": c["label"], "kind": "context", "source": "model", "in_context": None} for c in contexts]
        return Masked(chat_id, text, masked_text, span_out, contexts, latency_ms=(time.perf_counter() - t0) * 1000,
                      cost_usd=cost, tokens=tokens)


_LABEL = re.compile(r"<[A-Z][A-Z_]*_\d+>")


def rehydrate(text: str, mapping: dict[str, str]) -> tuple[str, list[str]]:
    """Replace placeholders with real values. Returns (text, labels that weren't in the vault)."""
    unknown: list[str] = []

    def sub(m: re.Match) -> str:
        label = m.group(0)
        if label in mapping:
            return mapping[label]
        unknown.append(label)
        return label

    return _LABEL.sub(sub, text), sorted(set(unknown))


def segments(text: str, chat_id: str, vault: Vault) -> list[dict]:
    """Split masked text into plain runs and restored placeholders, for highlighting in the UI (local only)."""
    out, cursor = [], 0
    for m in _LABEL.finditer(text):
        if m.start() > cursor:
            out.append({"text": text[cursor:m.start()]})
        label = m.group(0)
        target = vault._target(chat_id, label)
        value = vault.resolve(chat_id, label) if target else None
        out.append({"label": label, "kind": target[0] if target else "unknown", "text": value if value is not None else label})
        cursor = m.end()
    if cursor < len(text):
        out.append({"text": text[cursor:]})
    return out
