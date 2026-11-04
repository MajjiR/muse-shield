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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    # Values the model already saw unmasked earlier in this chat. Chat text keeps them (hiding them now would
    # only trip the pre-send guard), but a masked file copy must still hide them.
    already_sent: list[dict] = field(default_factory=list)
    # Classify mode: the document's categories (prompt and entity rules combined), a one-line summary.
    mode: str = "normal"
    categories: list[str] = field(default_factory=list)
    summary: str = ""

    def replacements(self) -> list[tuple[int, int, str]]:
        """(start, end, label) for every piece of `original` the masked text replaces, in order.
        Context blocks swallow the entities inside them."""
        out = [(c["start"], c["end"], c["label"]) for c in self.contexts]
        out += [(s["start"], s["end"], s["placeholder"]) for s in self.spans if s["kind"] == "entity" and not s.get("in_context")]
        return sorted(out)

    def to_dict(self) -> dict:
        return {"chat_id": self.chat_id, "masked_text": self.masked_text, "spans": self.spans, "contexts": self.contexts,
                "analysis_ok": self.analysis_ok, "error": self.error, "latency_ms": round(self.latency_ms, 1),
                "cost_usd": self.cost_usd, "mode": self.mode, "categories": self.categories, "summary": self.summary}


_TITLES = {"mr", "mrs", "ms", "mx", "dr", "prof", "shri", "smt", "sir", "madam", "adv"}
LINK_WINDOW = 80  # a contact or ID this close to a name (same paragraph) identifies that person


class Masker:
    def __init__(self, vault: Vault, analyzer: Backend, workers: int = 4):
        self.vault, self.analyzer, self.workers = vault, analyzer, workers

    def _analyze(self, paras: list[tuple[int, str]], on_progress=None) -> list[Analysis]:
        if not paras:
            return []
        with ThreadPoolExecutor(max_workers=min(self.workers, len(paras))) as pool:
            futures = [pool.submit(lambda p: self.analyzer.analyze([p[1]])[0], p) for p in paras]
            if on_progress:
                on_progress(0, len(futures))
                for done, _ in enumerate(as_completed(futures), 1):
                    on_progress(done, len(futures))
            return [f.result() for f in futures]

    @staticmethod
    def _propagate(text: str, entities: list[dict]) -> list[dict]:
        """Every other occurrence of a value the model found, with the same type and role (documents: the model
        may flag a name on page 1 and miss it on page 9)."""
        out, seen = [], set()
        for e in entities:
            value = e["text"].strip()
            key = (value.casefold(), e["type"], e["role"])
            if key in seen or (len(value) < 3 and e["type"] not in ALWAYS_MASK):
                continue
            seen.add(key)
            pattern = r"\s+".join(re.escape(w) for w in value.split())
            for m in re.finditer(rf"(?<!\w){pattern}(?!\w)", text, re.IGNORECASE):
                if "\n\n" not in m.group(0):
                    out.append({"start": m.start(), "end": m.end(), "text": m.group(0), "type": e["type"], "role": e["role"],
                                "canonical": e.get("canonical"), "owner": e.get("owner")})
        return out

    def _link_contacts(self, text: str, chat_id: str, spans: list[dict]) -> None:
        """Link each CONTACT/ID to the nearest PERSON within LINK_WINDOW characters, in the same paragraph."""
        people = [s for s in spans if s["type"] == "PERSON"]
        for c in (s for s in spans if s["type"] in ("CONTACT", "ID")):
            best, best_gap = None, LINK_WINDOW + 1
            for p in people:
                lo, hi = (p["end"], c["start"]) if p["end"] <= c["start"] else (c["end"], p["start"])
                gap = hi - lo
                if gap <= LINK_WINDOW and "\n\n" not in text[lo:hi] and gap < best_gap:
                    best, best_gap = p, gap
            if best:
                self.vault.add_edge(chat_id, c["placeholder"], best["placeholder"], "identifies")
                self.vault.link_entities(c["entity_id"], best["entity_id"], "identifies")

    def _known_people(self, chat_id: str) -> dict[str, str]:
        """PERSON values already in this chat: label -> value (to keep "Rohan" on turn 2 as Rohan Majji's label)."""
        return {label: value for label, value in self.vault.mapping(chat_id).items() if label.strip("<>").startswith("PERSON_")}

    @staticmethod
    def _same_person(e: dict, known: dict[str, str]) -> str:
        """The value to store this mention under: its resolved identity, or an earlier person in the chat whose
        full name contains it ("Rohan" or "Mr. Majji" after "Rohan Majji"), if exactly one matches."""
        value = e.get("canonical") or e["text"]
        if e["type"] != "PERSON":
            return value
        words = {w for w in re.findall(r"[\w']+", value.lower()) if w not in _TITLES}
        if not words or value in known.values():
            return value
        matches = {v for v in known.values() if words < set(re.findall(r"[\w']+", v.lower()))}
        return matches.pop() if len(matches) == 1 else value

    def _link_resolved(self, chat_id: str, spans: list[dict], relations: list, known: dict[str, str]) -> None:
        """Owners and relations from an entity-resolution model, as vault edges (instead of the distance heuristic)."""
        by_identity = {}
        for s in spans:
            by_identity.setdefault((s["type"], s.get("canonical") or s["text"]), s)
        for s in spans:
            owner = by_identity.get(tuple(s["owner"])) if s.get("owner") else None
            if not owner:
                continue
            rel = "identifies" if s["type"] in ("CONTACT", "ID") else "belongs_to"
            self.vault.add_edge(chat_id, s["placeholder"], owner["placeholder"], rel)
            if rel == "identifies":
                self.vault.link_entities(s["entity_id"], owner["entity_id"], "identifies")
        for a, rel, b in relations:
            sa, sb = by_identity.get(tuple(a)), by_identity.get(tuple(b))
            if sa and sb:
                self.vault.add_edge(chat_id, sa["placeholder"], sb["placeholder"], rel.lower())

    def mask(self, text: str, chat_id: str, *, propagate: bool = False, contexts: bool = True, on_progress=None,
             title: bool = True, mode: str = "normal") -> Masked:
        """Mask `text` for `chat_id`. Documents pass propagate=True (mask every occurrence of a found value),
        contexts=False (a passage block would swallow most of a page), on_progress(done, total) per analysed
        unit, and title=False (a document shouldn't name the chat).

        mode="classify" (entity-resolution analyzers only): a second call to the same model, run alongside the
        fill, classifies the document (medical, legal, hr, ...) and lists category-specific private details the
        fill doesn't cover (medications, case numbers, codenames, ratings). Those become <SENSITIVE_n>; the
        fill's own entities always win on overlap."""
        t0 = time.perf_counter()
        paras = paragraphs(text)
        classify = mode == "classify" and hasattr(self.analyzer, "classify_document")
        cls = None
        try:
            if hasattr(self.analyzer, "analyze_document"):  # entity resolution: one call sees the whole text
                if on_progress:
                    on_progress(0, 1)
                if classify and paras:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        pending = pool.submit(self.analyzer.classify_document, text)
                        analyses = self.analyzer.analyze_document(text, paras)
                        cls = pending.result()
                else:
                    analyses = self.analyzer.analyze_document(text, paras) if paras else []
                if on_progress:
                    on_progress(1, 1)
            else:
                analyses = self._analyze(paras, on_progress)
        except BackendError as exc:
            return Masked(chat_id, text, text, analysis_ok=False, error=f"analysis failed: {exc}",
                          latency_ms=(time.perf_counter() - t0) * 1000)
        bad = [a for a in analyses if not a.valid]
        tokens = {"in": 0, "out": 0, "cached_in": 0}
        for u in [a.usage for a in analyses] + ([cls["usage"]] if cls else []):
            tokens["in"] += u.get("prompt_tokens", 0)
            tokens["out"] += u.get("completion_tokens", 0)
            tokens["cached_in"] += u.get("prompt_tokens_details.cached_tokens", 0)
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
            for c in (a.contexts if contexts else []):
                lo, hi = min(c.sentences), max(c.sentences)
                start, end = off + offs[lo - 1][0], off + offs[hi - 1][1]
                if any(start < b["end"] and b["start"] < end for b in blocks):
                    continue  # overlapping blocks: keep the first
                blocks.append({"start": start, "end": end, "kind": c.kind, "subtype": c.subtype, "summary": c.summary})
            for s in a.entities:
                entities.append({"start": off + s.start, "end": off + s.end, "text": s.text, "type": s.type, "role": s.role,
                                 "canonical": getattr(s, "canonical", None), "owner": getattr(s, "owner", None)})
        relations = [r for a in analyses for r in getattr(a, "relations", [])]
        if propagate:
            entities += self._propagate(text, entities)
        categories, summary = [], ""
        if cls is not None:
            rule_cats = set(getattr(analyses[0], "categories", []) or []) if analyses else set()
            categories = sorted(set(cls["categories"]) | rule_cats) or ["general"]
            summary = cls["summary"]
            for x in cls["extras"]:
                for m in re.finditer(rf"(?<!\w){re.escape(x['text'])}(?!\w)", text):
                    entities.append({"start": m.start(), "end": m.end(), "text": m.group(0), "type": "SENSITIVE_ATTRIBUTE",
                                     "role": None, "canonical": None, "owner": None, "fallback": x["category"] or "sensitive"})

        # The fill's entities first, longest first; classify-mode fallbacks only where nothing else is.
        kept: list[dict] = []
        for e in sorted(entities, key=lambda e: (bool(e.get("fallback")), -(e["end"] - e["start"]))):
            if not any(e["start"] < k["end"] and k["start"] < e["end"] for k in kept):
                kept.append(e)
        kept.sort(key=lambda e: e["start"])

        # A value the model already saw unmasked in this chat can't be hidden after the fact; masking it now
        # would only make the pre-send guard refuse the chat (e.g. "the staging database password" masked on turn 2).
        mapped = set(self.vault.mapping(chat_id).values())
        seen = "\n".join(m["masked_text"] for m in self.vault.messages(chat_id))
        already_sent = [e for e in kept if e["text"] not in mapped and e["text"] in seen] if seen else []
        kept = [e for e in kept if e not in already_sent]

        spans: list[dict] = []
        resolved = any(e.get("canonical") for e in kept)
        known = self._known_people(chat_id) if resolved else {}
        for e in kept:
            value = self._same_person(e, known) if resolved else e["text"]
            base = "SENSITIVE" if e.get("fallback") else placeholder_base(e["type"], e["role"])
            label, entity_id = self.vault.entity_placeholder(chat_id, e["type"], value, base)
            spans.append({**e, "placeholder": label, "entity_id": entity_id, "kind": "entity",
                          "source": "fallback" if e.get("fallback") else "policy" if e["type"] in ALWAYS_MASK else "model"})
        if resolved:
            self._link_resolved(chat_id, spans, relations, known)
        else:
            self._link_contacts(text, chat_id, spans)

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

        result = Masked(chat_id, text, "", spans=spans, contexts=contexts, cost_usd=cost, tokens=tokens,
                        already_sent=[{k: e[k] for k in ("start", "end", "text", "type", "role")} for e in already_sent],
                        mode="classify" if cls is not None else "normal", categories=categories, summary=summary)
        pieces, cursor = [], 0
        for start, end, label in result.replacements():
            pieces += [text[cursor:start], label]
            cursor = end
        pieces.append(text[cursor:])
        masked_text = "".join(pieces)
        if title:
            self.vault.title_from_masked(chat_id, masked_text)

        labels = sorted({s["placeholder"] for s in spans})
        for a_, b_ in combinations(labels[:25], 2):
            self.vault.add_edge(chat_id, a_, b_, "appears_with")
        counts: dict[str, int] = {}
        for s in spans:
            counts[s["type"]] = counts.get(s["type"], 0) + 1
        for c in contexts:
            counts[f"CONTEXT_{c['kind']}"] = counts.get(f"CONTEXT_{c['kind']}", 0) + 1
        if already_sent:
            counts["ALREADY_SENT"] = len(already_sent)
        self.vault.audit("mask", chat_id, counts)

        span_out = [{k: s.get(k) for k in ("start", "end", "text", "type", "role", "placeholder", "kind", "source")} | {"in_context": s.get("in_context")}
                    | ({"fallback": s["fallback"]} if s.get("fallback") else {})
                    for s in spans]
        span_out += [{"start": c["start"], "end": c["end"], "text": text[c["start"]:c["end"]], "type": c["kind"], "role": None,
                      "placeholder": c["label"], "kind": "context", "source": "model", "in_context": None} for c in contexts]
        result.masked_text, result.spans = masked_text, span_out
        result.latency_ms = (time.perf_counter() - t0) * 1000
        return result


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
        if target and target[0] == "context":
            # Replies show a hidden passage as its summary; the full text is there for the user to expand.
            out.append({"label": label, "kind": "context", "text": vault.resolve(chat_id, label, "summary") or label,
                        "full": vault.resolve(chat_id, label)})
            cursor = m.end()
            continue
        value = vault.resolve(chat_id, label) if target else None
        out.append({"label": label, "kind": target[0] if target else "unknown", "text": value if value is not None else label})
        cursor = m.end()
    if cursor < len(text):
        out.append({"text": text[cursor:]})
    return out
