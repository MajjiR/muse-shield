"""LoRA training data for the on-device detector, personalized from Teach.

The local Llama detector is prompted with detector.llm.SYSTEM_PROMPT. This
module builds chat-format examples in exactly that format so a LoRA adapter
trained on them drops straight into the runtime prompt:

    system:    SYSTEM_PROMPT
    user:      <text>
    assistant: {"entities": [...], "confidential": bool, "reason": "..."}

Sources:
- generic synthetic examples (typed slots, wide name/org/codename pools,
  public-only negatives) so the adapter learns the task, not a word list;
- the user's taught terms, injected into templates with their taught type;
- the user's taught example sentences, labeled with their must-mask spans.

Training itself lives in scripts/lora_train.py (needs the [lora] extra).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .detector.llm import SYSTEM_PROMPT
from .entities import EntityType
from .personalization import PolicyStore

FIRST = ["Amara", "Bao", "Camila", "Dmitri", "Esi", "Farhan", "Greta", "Hiroshi", "Ifeoma", "Joaquín", "Kaveh", "Leilani",
         "Mateus", "Nadia", "Oluwaseun", "Pilar", "Quentin", "Rania", "Søren", "Tamar", "Uche", "Valentina", "Wiremu",
         "Ximena", "Yusuf", "Zofia", "Sarah", "David", "Priya", "Michael"]
LAST = ["Abara", "Bergström", "Castellanos", "Dlamini", "Eriksen", "Fujimoto", "Gallagher", "Haddad", "Iyer", "Jovanović",
        "Kowalczyk", "Lindqvist", "Mbeki", "Nakamura", "O'Connell", "Petrov", "Quispe", "Rahman", "Sato", "Tremblay",
        "Umarov", "Varga", "Whitfield", "Xu", "Yilmaz", "Zielinski", "Chen", "Okafor"]
ORG_STEMS = ["Northwind", "Kestrel", "Brightline", "Oakmont", "Tidewater", "Halcyon", "Corvid", "Lumen", "Stonebridge",
             "Bluefin", "Ardent", "Meridian", "Quarry", "Solace", "Vantage", "Ironwood"]
ORG_SUFFIX = ["", "", "", " Capital", " Labs", " Partners", " Health", " Bank", " Inc."]
CODENAMES = ["Bluebird", "Nightjar", "Moonstone", "Falcon", "Aurora", "Lantern", "Basalt", "Cobalt", "Juniper", "Mistral",
             "Sparrow", "Tundra", "Obsidian", "Halo"]
CITIES = ["Lagos", "Oslo", "Austin", "Pune", "Lisbon", "Osaka", "Denver", "Nairobi", "Seattle", "Montreal"]
PUBLIC_ORGS = ["Meta", "Google", "Nvidia", "Microsoft", "Apple", "Amazon"]
PUBLIC_TOPICS = ["Llama 4", "smart glasses", "open-source AI", "the new GPUs", "their earnings call"]

# (template, confidential, reason). Slots: {PERSON} {PERSON2} {ORG} {ORG2} {PROJECT} {LOCATION}
TEMPLATES = [
    ("Can you draft a note to {PERSON} at {ORG} about {PROJECT} slipping to Q3?", True, "internal project timeline"),
    ("{ORG} wants to acquire {ORG2} before the announcement. Summarize the risks for {PERSON}.", True, "unannounced acquisition"),
    ("Schedule a call between {PERSON} and {PERSON2} to review the {PROJECT} roadmap.", True, "internal roadmap"),
    ("{PERSON} from {ORG} is relocating the {PROJECT} team to {LOCATION}.", True, "internal reorganization"),
    ("Write a thank-you email to {PERSON} for hosting us in {LOCATION}.", False, ""),
    ("Our board deck says {PROJECT} margins beat plan. Tighten the wording for {PERSON}.", True, "internal financials"),
    ("Translate this for {PERSON}: the {ORG} pilot starts Monday.", True, "customer pilot details"),
    ("Remind {PERSON} that {ORG2} signed the term sheet.", True, "deal terms"),
]
PUBLIC_TEMPLATES = [
    "What did {PUBLIC_ORG} announce about {TOPIC}?",
    "Explain how {TOPIC} works in simple terms.",
    "Is {PUBLIC_ORG} stock a good long-term hold? Give both sides.",
    "Write a haiku about debugging at 3am.",
]


def _org(rng: random.Random) -> str:
    return rng.choice(ORG_STEMS) + rng.choice(ORG_SUFFIX)


def _fill(template: str, rng: random.Random, overrides: dict[str, tuple[str, EntityType]] | None = None):
    """Fill slots; return (text, [(span, type)])."""
    slots = {
        "PERSON": lambda: (f"{rng.choice(FIRST)} {rng.choice(LAST)}", EntityType.PERSON),
        "PERSON2": lambda: (f"{rng.choice(FIRST)} {rng.choice(LAST)}", EntityType.PERSON),
        "ORG": lambda: (_org(rng), EntityType.ORG),
        "ORG2": lambda: (_org(rng), EntityType.ORG),
        "PROJECT": lambda: (rng.choice(["Project ", ""]) + rng.choice(CODENAMES), EntityType.PROJECT),
        "LOCATION": lambda: (rng.choice(CITIES), EntityType.LOCATION),
        "PUBLIC_ORG": lambda: (rng.choice(PUBLIC_ORGS), EntityType.ORG),
        "TOPIC": lambda: (rng.choice(PUBLIC_TOPICS), None),
    }
    values = {}
    for name, make in slots.items():
        if "{" + name + "}" in template:
            values[name] = (overrides or {}).get(name) or make()
    text = template.format(**{k: v[0] for k, v in values.items()})
    spans = [(v, t) for v, t in values.values() if t is not None]
    return text, spans


def example(text: str, spans: list[tuple[str, EntityType]], confidential: bool, reason: str = "") -> dict:
    seen, entities = set(), []
    for span, etype in spans:
        span = span.strip(".,;:'\"")  # same normalization as the runtime parser
        if span in text and span not in seen:
            seen.add(span)
            entities.append({"text": span, "type": etype.value})
    target = {"entities": entities, "confidential": confidential, "reason": reason if confidential else ""}
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
            {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
        ]
    }


def build_dataset(n: int = 600, seed: int = 11, store: PolicyStore | None = None, personal_weight: float = 0.35) -> list[dict]:
    rng = random.Random(seed)
    taught = list((store.active.terms if store else {}).items())
    out: list[dict] = []

    # 1) The user's own example sentences, verbatim (repeated: they are few and precious).
    if store:
        for case in store.examples:
            spans = [(s, store.active.terms.get(s, EntityType.CONFIDENTIAL_TERM)) for s in case.must_mask]
            for _ in range(3):
                out.append(example(case.text, spans, bool(spans), "user-taught sensitive context"))

    slot_for = {EntityType.PERSON: "PERSON", EntityType.ORG: "ORG", EntityType.PROJECT: "PROJECT", EntityType.LOCATION: "LOCATION"}
    while len(out) < n:
        r = rng.random()
        if r < 0.2:
            text, spans = _fill(rng.choice(PUBLIC_TEMPLATES), rng)
            out.append(example(text, spans, False))
            continue
        template, confidential, reason = rng.choice(TEMPLATES)
        overrides = {}
        # 2) Personalization: put taught terms into real-looking sentences.
        if taught and r < 0.2 + personal_weight:
            term, etype = rng.choice(taught)
            slot = slot_for.get(etype, "PROJECT")
            if "{" + slot + "}" in template:
                overrides[slot] = (term, etype if etype in slot_for else EntityType.CONFIDENTIAL_TERM)
        text, spans = _fill(template, rng, overrides)
        out.append(example(text, spans, confidential, reason))
    rng.shuffle(out)
    return out[:n]


def export(out_dir: Path, n: int = 600, seed: int = 11, store: PolicyStore | None = None, val_fraction: float = 0.1) -> dict:
    rows = build_dataset(n, seed, store)
    k = max(1, int(len(rows) * val_fraction))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, chunk in (("val", rows[:k]), ("train", rows[k:])):
        with (out_dir / f"{name}.jsonl").open("w") as f:
            for row in chunk:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"train": len(rows) - k, "val": k, "dir": str(out_dir), "taught_terms": len(store.active.terms) if store else 0}
