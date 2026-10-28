"""Benchmark: how much privacy do we buy, and how much AI utility do we pay for it?

A seeded synthetic dataset (no real people) with gold spans is pushed through
several outbound strategies:

    raw          send the prompt as-is (utility ceiling, privacy floor)
    redact       replace every detected span with [REDACTED]
    pii-only     semantic tokens for PII, confidential context passes through
    semantic     the default policy (PII + confidential, context-aware)
    strict       semantic tokens for everything detected, public included

Privacy  leak rate      gold sensitive spans that appear in the outbound text
         over-masking   gold public spans that were hidden from the model
Utility  (offline, model-free proxies of what the cloud model can still do)
         distinct       different entities stay distinguishable (PERSON_1 vs PERSON_2)
         magnitude      a money comparison is still answerable from the masked text
         context        public context the question is about is still visible
         restorable     the original prompt can be rebuilt locally from the output
With --online, each strategy's prompt also goes to the configured cloud model
and the reconstructed answer is scored against the raw-prompt answer (LCS F1)
and for whether it names the right entities. Online mode sends the synthetic
raw prompts to the cloud as the baseline; never point it at real data.
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .detector import Detector
from .entities import Entity, EntityType, Sensitivity
from .masking import SessionAllocator, mask
from .policy import Action, Policy, evaluate
from .reconstruct import reconstruct
from .values import parse_money

# -- synthetic data -------------------------------------------------------------

LEXICON_NAMES = ["Sarah Chen", "David Okafor", "Priya Raman", "Michael Torres", "Emily Novak", "Wei Zhang", "Laura Ibsen"]
RARE_NAMES = ["Xiomara Quist", "Bartholomew Ngata", "Ingrid Vasquez-Lowe", "Tobias Achterberg", "Nkechi Adeyemi"]
SUFFIX_ORGS = ["Northwind Capital", "Halcyon Partners", "Globex Corp", "Initech Holdings", "Vandelay Ventures"]
BARE_ORGS = ["Kestrel", "Brightline", "Oakmont", "Tidewater"]
PROJECTS = ["Project Falcon", "Project Aurora", "Operation Lantern"]
BARE_CODENAMES = ["Bluebird", "Nightjar", "Moonstone"]
PUBLIC_ORGS = ["Meta", "Google", "Nvidia", "Microsoft"]
PUBLIC_TOPICS = ["Llama", "open-source models", "smart glasses", "GPU supply"]
BIG = ["$1.2B", "$850M", "$2.4B", "$300M"]
MID = ["$12M", "$45M", "$7.5M"]
SMALL = ["$450,000", "$80,000", "$3,500"]
PETTY = ["$20", "$35", "$12"]


@dataclass
class Sample:
    text: str
    kind: str
    sensitive: list[str]
    public: list[str] = field(default_factory=list)
    distinct: list[str] = field(default_factory=list)  # same-type entities that must stay distinguishable
    compare: tuple[str, str] | None = None  # two amounts whose order must stay answerable


def _email(name: str, org: str) -> str:
    first = name.split()[0].lower()
    domain = re.sub(r"[^a-z]", "", org.lower().split()[0])
    return f"{first}@{domain}.io"


def _phone(rng: random.Random) -> str:
    return f"({rng.randint(201, 989)}) 555-{rng.randint(1000, 9999)}"


def _card(rng: random.Random) -> str:
    digits = [4] + [rng.randint(0, 9) for _ in range(14)]
    total = 0
    for i, d in enumerate(reversed(digits)):  # compute Luhn check digit
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    digits.append((10 - total % 10) % 10)
    s = "".join(map(str, digits))
    return " ".join(s[i : i + 4] for i in range(0, 16, 4))


def generate(n: int = 120, seed: int = 7) -> list[Sample]:
    rng = random.Random(seed)
    pick = rng.choice

    def person():
        return pick(RARE_NAMES) if rng.random() < 0.3 else pick(LEXICON_NAMES)

    def org():
        return pick(BARE_ORGS) if rng.random() < 0.3 else pick(SUFFIX_ORGS)

    def project():
        return pick(BARE_CODENAMES) if rng.random() < 0.3 else pick(PROJECTS)

    def email():
        p, o, pr, amt = person(), org(), project(), pick(BIG + MID)
        e = _email(p, o)
        return Sample(f"Draft an email to {p} at {e} about the {amt} offer from {o} for {pr}.", "email", [p, e, amt, o, pr])

    def deal():
        o1, o2 = rng.sample(SUFFIX_ORGS + BARE_ORGS, 2)
        p, amt = person(), pick(BIG)
        return Sample(f"Confidential: {o1} plans to acquire {o2} for {amt}. {p} leads the deal. Summarize the risks.",
                      "summary", [o1, o2, amt, p], distinct=[o1, o2])

    def compare():
        o1, o2 = rng.sample(SUFFIX_ORGS, 2)
        big, small = pick(BIG), pick(SMALL)
        a, b = (big, small) if rng.random() < 0.5 else (small, big)
        return Sample(f"Confidential: {o1} offered {a} and {o2} offered {b}. Which offer is larger, and roughly by how much?",
                      "compare", [o1, o2, a, b], distinct=[o1, o2], compare=(a, b))

    def public_qa():
        o, t = pick(PUBLIC_ORGS), pick(PUBLIC_TOPICS)
        return Sample(f"What did {o} announce about {t} this year?", "public", [], public=[o, t])

    def dispute():
        c, o, ph = _card(rng), org(), _phone(rng)
        return Sample(f"My card {c} was charged twice by {o}. Call me at {ph}. Write a dispute letter.", "pii", [c, o, ph])

    def meeting():
        p1, p2 = rng.sample(LEXICON_NAMES + RARE_NAMES, 2)
        pr = project()
        return Sample(f"Schedule a meeting between {p1} and {p2} to review {pr}.", "meeting", [p1, p2, pr], distinct=[p1, p2])

    def petty():
        amt = pick(PETTY)
        return Sample(f"I spent {amt} on lunch with friends, is that normal?", "public", [], public=[amt])

    def secret():
        key = "sk-proj-" + "".join(pick("abcdefghijkmnpqrstuvwxyz0123456789") for _ in range(24))
        return Sample(f"Here is my API key {key}, why does every request return 401?", "secret", [key])

    makers: list[Callable[[], Sample]] = [email, deal, compare, public_qa, dispute, meeting, petty, secret]
    return [makers[i % len(makers)]() for i in range(n)]


# -- strategies -------------------------------------------------------------------


class _RedactAllocator:
    def token_for(self, entity: Entity) -> str:
        return "[REDACTED]"


def _policies() -> dict[str, Policy]:
    pii_only = Policy(name="pii-only")
    pii_only.actions[Sensitivity.CONFIDENTIAL] = Action.ALLOW
    strict = Policy(name="strict")
    strict.actions[Sensitivity.PUBLIC] = Action.MASK
    # What a user gets after a few minutes in Teach: their own codenames and clients.
    taught = Policy(name="semantic+taught")
    taught.terms = {**{o: EntityType.ORG for o in BARE_ORGS}, **{c: EntityType.PROJECT for c in BARE_CODENAMES}}
    return {"pii-only": pii_only, "semantic": Policy(name="semantic"), "semantic+taught": taught, "strict": strict}


STRATEGIES = ["raw", "redact", "pii-only", "semantic", "semantic+taught", "strict"]


@dataclass
class Outbound:
    text: str
    mapping: dict[str, str]


def outbound(strategy: str, sample: Sample, detector: Detector, use_llm: bool) -> Outbound:
    if strategy == "raw":
        return Outbound(sample.text, {})
    policy = Policy() if strategy == "redact" else _policies()[strategy]
    det = detector.detect(sample.text, terms=policy.terms, cues=policy.cues, use_llm=use_llm)
    result = evaluate(det, policy)
    if strategy == "redact":
        m = mask(sample.text, result, _RedactAllocator())
        return Outbound(m.masked, {})
    m = mask(sample.text, result, SessionAllocator())
    return Outbound(m.masked, m.mapping)


# -- metrics ----------------------------------------------------------------------


def _present(span: str, text: str) -> bool:
    return span.casefold() in text.casefold()


def _token_of(span: str, out: Outbound) -> str | None:
    for token, value in out.mapping.items():
        if value.casefold() == span.casefold():
            return token
    return None


_ORDER = ["SMALL", "MEDIUM", "LARGE", "MAJOR"]


def _magnitude_answerable(a: str, b: str, out: Outbound) -> bool:
    if _present(a, out.text) and _present(b, out.text):
        return True
    ta, tb = _token_of(a, out), _token_of(b, out)
    if not ta or not tb:
        return False
    ra = next((i for i, w in enumerate(_ORDER) if ta.startswith(w)), None)
    rb = next((i for i, w in enumerate(_ORDER) if tb.startswith(w)), None)
    # Answerable from tokens alone only if they land in different buckets.
    return ra is not None and rb is not None and ra != rb and (parse_money(a) > parse_money(b)) == (ra > rb)


def score(sample: Sample, out: Outbound) -> dict:
    s: dict[str, float | None] = {}
    s["leaked"] = sum(_present(x, out.text) for x in sample.sensitive)
    s["sensitive"] = len(sample.sensitive)
    s["over_masked"] = sum(not _present(x, out.text) for x in sample.public)
    s["public"] = len(sample.public)

    if sample.distinct:
        reps = []
        for x in sample.distinct:
            reps.append(x.casefold() if _present(x, out.text) else _token_of(x, out))
        s["distinct"] = float(None not in reps and len(set(reps)) == len(reps))
    if sample.compare:
        s["magnitude"] = float(_magnitude_answerable(*sample.compare, out))
    if sample.public:
        s["context"] = 1.0 - s["over_masked"] / len(sample.public)
    s["restorable"] = float(reconstruct(out.text, out.mapping).text == sample.text)
    return s


def _lcs_f1(a: str, b: str) -> float:
    x, y = a.lower().split(), b.lower().split()
    if not x or not y:
        return 0.0
    prev = [0] * (len(y) + 1)
    for xi in x:
        cur = [0]
        for j, yj in enumerate(y):
            cur.append(prev[j] + 1 if xi == yj else max(prev[j + 1], cur[j]))
        prev = cur
    lcs = prev[-1]
    p, r = lcs / len(x), lcs / len(y)
    return 0.0 if lcs == 0 else 2 * p * r / (p + r)


# -- runner -----------------------------------------------------------------------


def run(n: int = 120, seed: int = 7, use_llm: bool = False, detector: Detector | None = None,
        online: Callable[[str], str] | None = None, online_n: int = 16) -> dict:
    detector = detector or Detector()
    samples = generate(n, seed)
    rows: dict[str, dict] = {}
    per_type_missed: dict[str, int] = {}
    t0 = time.perf_counter()

    for strategy in STRATEGIES:
        agg: dict[str, list[float]] = {}
        leaked = sensitive = over = public = 0
        outs = []
        for sample in samples:
            out = outbound(strategy, sample, detector, use_llm)
            outs.append(out)
            sc = score(sample, out)
            leaked += sc.pop("leaked")
            sensitive += sc.pop("sensitive")
            over += sc.pop("over_masked")
            public += sc.pop("public")
            for k, v in sc.items():
                agg.setdefault(k, []).append(v)
            if strategy == "semantic+taught":
                for x in sample.sensitive:
                    if _present(x, out.text):
                        per_type_missed[sample.kind] = per_type_missed.get(sample.kind, 0) + 1
        utility = {k: sum(v) / len(v) for k, v in agg.items()}
        model_free = [utility[k] for k in ("distinct", "magnitude", "context") if k in utility]
        rows[strategy] = {
            "leak_rate": leaked / max(sensitive, 1),
            "over_mask_rate": over / max(public, 1),
            **utility,
            "utility": sum(model_free) / len(model_free),
        }
        if online:
            rows[strategy].update(_online_scores(samples[:online_n], outs[:online_n], online))

    return {
        "n": n,
        "seed": seed,
        "detector": "rules + llama" if use_llm else "rules",
        "seconds": round(time.perf_counter() - t0, 2),
        "strategies": rows,
        "semantic_misses_by_kind": per_type_missed,
    }


_RAW_ANSWERS: dict[str, str] = {}


def _online_scores(samples: list[Sample], outs: list[Outbound], ask: Callable[[str], str]) -> dict:
    sims, mentions = [], []
    for sample, out in zip(samples, outs):
        if sample.text not in _RAW_ANSWERS:
            _RAW_ANSWERS[sample.text] = ask(sample.text)
        answer = reconstruct(ask(out.text), out.mapping).text if out.text != sample.text else _RAW_ANSWERS[sample.text]
        sims.append(_lcs_f1(answer, _RAW_ANSWERS[sample.text]))
        named = [x for x in sample.sensitive if _present(x, _RAW_ANSWERS[sample.text])]
        if named:
            mentions.append(sum(_present(x, answer) for x in named) / len(named))
    return {
        "answer_similarity": sum(sims) / len(sims),
        "entity_recall": sum(mentions) / len(mentions) if mentions else None,
    }


def render(report: dict) -> str:
    rows = report["strategies"]
    cols = [("leak_rate", "leak ↓"), ("over_mask_rate", "over-mask ↓"), ("distinct", "distinct ↑"),
            ("magnitude", "magnitude ↑"), ("context", "context ↑"), ("restorable", "restorable ↑"), ("utility", "utility ↑")]
    if any("answer_similarity" in r for r in rows.values()):
        cols += [("answer_similarity", "answer sim ↑"), ("entity_recall", "entity recall ↑")]
    head = "| strategy | " + " | ".join(c[1] for c in cols) + " |"
    sep = "|---" * (len(cols) + 1) + "|"
    lines = [head, sep]
    for name, r in rows.items():
        cells = [f"{r[k]:.0%}" if isinstance(r.get(k), float) else "–" for k, _ in cols]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    misses = ", ".join(f"{k}: {v}" for k, v in sorted(report["semantic_misses_by_kind"].items())) or "none"
    lines += ["", f"n={report['n']} seed={report['seed']} detector={report['detector']} · {report['seconds']}s",
              f"semantic+taught leaks by prompt kind: {misses}"]
    return "\n".join(lines)


def save(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"bench-{stamp}.json").write_text(json.dumps(report, indent=2))
    path = out_dir / f"bench-{stamp}.md"
    path.write_text("# Privacy vs utility\n\n" + render(report) + "\n")
    return path
