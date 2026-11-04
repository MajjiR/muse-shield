"""Entity resolution: the document-level contract, mention locator, registry, masker and scorer.

Stage-1 analysis asks "which strings are sensitive?" one paragraph at a time. This asks the
document-level questions as well:
- which mentions are the same person or organisation (Rohan Majji, Rohan, Mr Majji, he, his),
- whose private value is this (owner: Rohan's salary vs Sandeep's salary, or UNKNOWN),
- how the people relate (MANAGES, PARENT_OF, REPRESENTS, ...).

The model never returns character offsets. It returns entities, each with its mentions as
[unit number, exact text]; code finds each mention in its unit, in order. Code also mints the
placeholders and does the masking, so a model mistake can drop a mention but can't corrupt the
document or give one person two identities.

Masking policy: names and private values are replaced by their placeholder (<PERSON_1>,
<SALARY_1>). References (pronouns and descriptions like "his mother", "the employee") stay as
written: they don't identify anyone on their own, and keeping them keeps the text readable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from muse_shield.analysis import AMOUNT_ROLES, ENTITY_TYPES, ContractError, _loads, split_sentences

ID_SUBTYPES = {
    "ID": {"AADHAAR", "PAN", "PASSPORT", "SSN", "BANK_ACCOUNT", "IFSC", "CARD", "EMPLOYEE_ID", "CUSTOMER_ID",
           "MEDICAL_RECORD", "TAX_ID", "POLICY", "OTHER"},
    "CONTACT": {"PHONE", "EMAIL"},
    "ADDRESS": {"RESIDENTIAL", "OFFICE", "OTHER"},
    "DATE": {"DOB", "JOINING", "EXIT", "DEADLINE", "EVENT", "OTHER"},
    "SENSITIVE_ATTRIBUTE": {"HEALTH", "AGE", "GENDER", "RELIGION", "CASTE_ETHNICITY", "POLITICS", "SEXUALITY",
                            "BODY_MEASUREMENT", "DISABILITY", "OTHER"},
}
# v3 adds web and device identifiers, places, times and secrets (they were all leaking on public benchmarks)
ID_SUBTYPES["CONTACT"] |= {"URL", "USERNAME", "OTHER"}
ID_SUBTYPES["ID"] |= {"IP_ADDRESS", "DEVICE", "VEHICLE", "LICENSE"}
ID_SUBTYPES["DATE"] |= {"TIME"}
ID_SUBTYPES["LOCATION"] = {"CITY", "STATE", "COUNTRY", "OTHER"}
ID_SUBTYPES["SECRET"] = {"PASSWORD", "API_KEY", "PIN", "OTHER"}
OWNED_TYPES = {"AMOUNT", "ADDRESS", "ID", "CONTACT", "DATE", "SENSITIVE_ATTRIBUTE", "SECRET", "LOCATION"}
RELATIONS = {"MANAGES", "EMPLOYED_BY", "SPOUSE_OF", "PARENT_OF", "SIBLING_OF", "EMERGENCY_CONTACT_OF", "REPRESENTS",
             "TREATS", "GUARANTOR_FOR", "NOMINEE_OF", "LANDLORD_OF", "CLIENT_OF"}
ALWAYS_MASK = {"PERSON", "ID", "CONTACT", "SECRET", "ADDRESS"}
CORE_TYPES = ALWAYS_MASK
UNKNOWN = "UNKNOWN"

# A mention starting with one of these refers to someone without naming them ("his", "her mother",
# "the employee"): kept as written, never masked.
_REFERENCE_WORDS = {"he", "she", "him", "his", "her", "hers", "himself", "herself", "they", "them", "their", "theirs",
                    "themselves", "the", "this", "that", "our", "your", "my", "its", "it", "we", "us", "i", "me",
                    "you", "yours", "yourself", "who", "whom", "whose"}


def is_reference(text: str) -> bool:
    first = re.split(r"[\s']", text.strip(), maxsplit=1)[0].lower().strip(".,;:")
    return first in _REFERENCE_WORDS


# -- units ------------------------------------------------------------------------------------

def units(text: str) -> list[tuple[int, int]]:
    """Split a document into numbered units: one per table row or line, long lines split into sentences."""
    out: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        start, stripped = pos, line.strip()
        pos += len(line) + 1
        if not stripped:
            continue
        if stripped.startswith("|") or len(stripped) < 200 and not re.search(r"[.!?]\s+[A-Z]", stripped):
            off = line.index(stripped)
            out.append((start + off, start + off + len(stripped)))
            continue
        cursor = 0
        for sent in split_sentences(line):
            i = line.find(sent, cursor)
            if i < 0:
                continue
            out.append((start + i, start + i + len(sent)))
            cursor = i + len(sent)
    return out


def render_units(text: str, us: list[tuple[int, int]] | None = None) -> str:
    us = units(text) if us is None else us
    return "\n".join(f"[{i}] {text[s:e]}" for i, (s, e) in enumerate(us, 1))


# -- the prompt -------------------------------------------------------------------------------

SYSTEM_PROMPT = """You resolve the people, organisations and private details in a document for a privacy gateway.
The document is split into numbered units [n]. Return ONE JSON object and nothing else:
{"entities": [{"id": "...", "type": "...", "role": "...", "subtype": "...", "owner": "...", "mentions": [[unit, "exact text"], ...]}],
 "relations": [["from id", "RELATION", "to id"]]}

- One entity per real person, organisation or private value. List EVERY mention of it in document order as
  [unit number, exact text copied from that unit]: full name, first name, title + surname, pronouns (he, his,
  her, they) and descriptions ("the employee", "her mother") that refer to it. A mention that occurs twice is listed twice.
- type: PERSON, ORG, ADDRESS, LOCATION, AMOUNT, PROJECT, ID, CONTACT, DATE, SECRET or SENSITIVE_ATTRIBUTE.
- id: the type plus a number in order of first appearance (PERSON_1, ORG_1, ID_2). An AMOUNT uses its role
  instead (SALARY_1, LOAN_1).
- role: for PERSON and ORG, their role in this document in 1-3 lowercase words (employee, manager, mother,
  borrower, employer, lender). For AMOUNT: SALARY (pay, bonus, stipend, allowance), PRICE (what something costs to
  buy, rent or insure: rent, purchase price, premium), FEE (deposits, charges, tuition, professional fees), LOAN
  (loans, EMIs, arrears), DEAL_VALUE, REVENUE, BUDGET, or OTHER (claims, settlements, reimbursements).
- subtype: ID: AADHAAR, PAN, PASSPORT, SSN, BANK_ACCOUNT, IFSC, CARD, EMPLOYEE_ID, CUSTOMER_ID, MEDICAL_RECORD,
  TAX_ID, POLICY, OTHER. CONTACT: PHONE, EMAIL. ADDRESS: RESIDENTIAL, OFFICE, OTHER. DATE: DOB, JOINING, EXIT,
  DEADLINE, EVENT, OTHER. SENSITIVE_ATTRIBUTE: HEALTH, AGE, GENDER, RELIGION, CASTE_ETHNICITY, POLITICS,
  SEXUALITY, BODY_MEASUREMENT, DISABILITY, OTHER.
- owner: for AMOUNT, ADDRESS, ID, CONTACT, DATE, SENSITIVE_ATTRIBUTE and SECRET, the id of the person or
  organisation it belongs to. If the text does not make the owner clear, use "UNKNOWN". Never guess.
- relations: only what the text states, with RELATION one of MANAGES, EMPLOYED_BY, SPOUSE_OF, PARENT_OF,
  SIBLING_OF, EMERGENCY_CONTACT_OF, REPRESENTS, TREATS, GUARANTOR_FOR, NOMINEE_OF, LANDLORD_OF, CLIENT_OF.
- Specific dates only (not "next quarter"). Job titles and public facts are not private values.
- If nothing qualifies, return {"entities": [], "relations": []}."""

EXAMPLE_USER = render_units(
    "Rohan Majji joined Acme Technologies as a Software Engineer on 3 March 2025. His annual compensation is ₹24 LPA.\n"
    "He reports to Sandeep Kumar, whose compensation is ₹32 LPA. Rohan's emergency contact is his mother, "
    "Lakshmi Majji (+91 98450 12345).")
EXAMPLE_ASSISTANT = json.dumps({
    "entities": [
        {"id": "PERSON_1", "type": "PERSON", "role": "employee",
         "mentions": [[1, "Rohan Majji"], [2, "His"], [3, "He"], [4, "Rohan"], [4, "his"]]},
        {"id": "ORG_1", "type": "ORG", "role": "employer", "mentions": [[1, "Acme Technologies"]]},
        {"id": "DATE_1", "type": "DATE", "subtype": "JOINING", "owner": "PERSON_1", "mentions": [[1, "3 March 2025"]]},
        {"id": "SALARY_1", "type": "AMOUNT", "role": "SALARY", "owner": "PERSON_1", "mentions": [[2, "₹24 LPA"]]},
        {"id": "PERSON_2", "type": "PERSON", "role": "manager", "mentions": [[3, "Sandeep Kumar"], [3, "whose"]]},
        {"id": "SALARY_2", "type": "AMOUNT", "role": "SALARY", "owner": "PERSON_2", "mentions": [[3, "₹32 LPA"]]},
        {"id": "PERSON_3", "type": "PERSON", "role": "mother", "mentions": [[4, "his mother"], [4, "Lakshmi Majji"]]},
        {"id": "CONTACT_1", "type": "CONTACT", "subtype": "PHONE", "owner": "PERSON_3", "mentions": [[4, "+91 98450 12345"]]},
    ],
    "relations": [["PERSON_1", "EMPLOYED_BY", "ORG_1"], ["PERSON_2", "MANAGES", "PERSON_1"],
                  ["PERSON_3", "PARENT_OF", "PERSON_1"], ["PERSON_3", "EMERGENCY_CONTACT_OF", "PERSON_1"]],
}, ensure_ascii=False)


# v3 policy (er-v3 models): anything that can point back to a person is private, including the places, organisations,
# links and times around them. Public benchmarks (Nemotron-PII, PUPA) count all of these; v2 left them readable.
SYSTEM_PROMPT_V3 = SYSTEM_PROMPT.replace(
    "  TAX_ID, POLICY, OTHER. CONTACT: PHONE, EMAIL. ADDRESS: RESIDENTIAL, OFFICE, OTHER. DATE: DOB, JOINING, EXIT,\n"
    "  DEADLINE, EVENT, OTHER.",
    "  TAX_ID, POLICY, IP_ADDRESS, DEVICE, VEHICLE, LICENSE, OTHER. CONTACT: PHONE, EMAIL, URL, USERNAME, OTHER.\n"
    "  ADDRESS: RESIDENTIAL, OFFICE, OTHER. DATE: DOB, JOINING, EXIT, DEADLINE, EVENT, TIME, OTHER. LOCATION: CITY,\n"
    "  STATE, COUNTRY, OTHER. SECRET: PASSWORD, API_KEY, PIN, OTHER.",
).replace(
    "- owner: for AMOUNT, ADDRESS, ID, CONTACT, DATE, SENSITIVE_ATTRIBUTE and SECRET,",
    "- owner: for AMOUNT, ADDRESS, ID, CONTACT, DATE, LOCATION, SENSITIVE_ATTRIBUTE and SECRET,",
).replace(
    "- Specific dates only (not \"next quarter\"). Job titles and public facts are not private values.",
    "- Also private, because they point back to the people in the text or the user: web addresses and profile links,\n"
    "  usernames and handles (CONTACT); IP and MAC addresses, device, vehicle and licence numbers (ID); passwords, PINs,\n"
    "  API keys and cookies (SECRET); cities, states, countries and other places (LOCATION); employers, schools,\n"
    "  banks, hospitals, brands, apps and every other organisation they deal with (ORG); times of day (DATE, TIME);\n"
    "  gender, religion, politics, ethnicity and sexuality (SENSITIVE_ATTRIBUTE).\n"
    "- Specific dates and times only (not \"next quarter\"). Job titles are not private values. Placeholders already\n"
    "  in the text (<PERSON_1>) are not entities.",
)
assert SYSTEM_PROMPT_V3.count("LOCATION: CITY") == 1 and "web addresses" in SYSTEM_PROMPT_V3 and "LOCATION, SENSITIVE" in SYSTEM_PROMPT_V3
# Rows converted from span-only datasets (Nemotron-PII) have no pronouns, roles, owners or relations: they say so.
VALUES_ONLY_NOTE = ("\n- Short form for this document: list every name and private value with all its mentions; pronouns,"
                    " descriptions, roles, owners and relations may be left out.")


def messages(text: str, example: bool = True, version: str = "v2", values_only: bool = False) -> list[dict]:
    """The prompt. Fine-tuned models skip the worked example (they were trained without it: ~600 fewer tokens).
    version "v3" is the er-v3 policy prompt; values_only marks span-only training rows."""
    system = SYSTEM_PROMPT_V3 if version == "v3" else SYSTEM_PROMPT
    if values_only:
        system += VALUES_ONLY_NOTE
    shot = [{"role": "user", "content": EXAMPLE_USER}, {"role": "assistant", "content": EXAMPLE_ASSISTANT}] if example else []
    return [{"role": "system", "content": system}, *shot, {"role": "user", "content": render_units(text)}]


def prompt_version(model: str) -> str:
    """er-v3 adapters (and their checkpoints) were trained on the v3 prompt; everything else on v2."""
    return "v3" if "er-v3" in (model or "") else "v2"


# -- parsing and grounding --------------------------------------------------------------------

@dataclass
class Mention:
    start: int
    end: int
    text: str
    unit: int
    reference: bool


@dataclass
class Entity:
    id: str
    type: str
    role: str | None = None
    subtype: str | None = None
    owner: str | None = None
    mentions: list[Mention] = field(default_factory=list)


@dataclass
class Resolution:
    text: str
    entities: list[Entity]
    relations: list[tuple[str, str, str]]
    valid: bool = True
    error: str = ""
    dropped: int = 0  # mentions that could not be found in their unit


def _find(unit_text: str, needle: str, after: int) -> int:
    """Next occurrence of needle at or after `after`, on word boundaries where the needle has word edges."""
    pat = re.escape(needle)
    if needle[:1].isalnum():
        pat = r"(?<![\w])" + pat
    if needle[-1:].isalnum():
        pat += r"(?![\w])"
    for flags in (0, re.IGNORECASE):
        m = re.compile(pat, flags).search(unit_text, after)
        if m:
            return m.start()
        m = re.compile(pat, flags).search(unit_text)  # out of order: take the first one
        if m and flags:
            return m.start()
    return -1


def parse(raw: str, text: str) -> Resolution:
    """Validate and ground a model reply. Raises ContractError only when nothing usable came back."""
    data = _loads(raw)
    ents, rels = data.get("entities"), data.get("relations", [])
    if not isinstance(ents, list) or not isinstance(rels, list):
        raise ContractError("entities and relations must be lists")
    us = units(text)
    out = Resolution(text, [], [])
    cursors: dict[tuple[int, str], int] = {}
    taken: set[tuple[int, int]] = set()
    seen: set[str] = set()
    for item in ents:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ContractError(f"bad entity: {item!r:.80}")
        etype = str(item.get("type", "")).upper()
        if etype not in ENTITY_TYPES:
            raise ContractError(f"unknown type {etype!r}")
        eid = item["id"].strip().upper()
        if eid in seen:
            raise ContractError(f"duplicate id {eid}")
        seen.add(eid)
        role = item.get("role")
        role = (role.upper() if etype == "AMOUNT" else role.lower()) if isinstance(role, str) and role.strip() else None
        if etype == "AMOUNT" and role not in AMOUNT_ROLES:
            role = "OTHER"
        sub = item.get("subtype")
        sub = sub.upper() if isinstance(sub, str) and sub.upper() in ID_SUBTYPES.get(etype, set()) else None
        owner = item.get("owner")
        owner = owner.strip().upper() if isinstance(owner, str) and owner.strip() and etype in OWNED_TYPES else None
        ent = Entity(eid, etype, role, sub, owner)
        for m in item.get("mentions") or []:
            if not (isinstance(m, list) and len(m) == 2 and isinstance(m[0], int) and isinstance(m[1], str) and m[1].strip()):
                out.dropped += 1
                continue
            u, mtext = m[0], m[1].strip()
            if not 1 <= u <= len(us):
                out.dropped += 1
                continue
            us_s, us_e = us[u - 1]
            utext = text[us_s:us_e]
            key = (u, mtext.lower())
            i = _find(utext, mtext, cursors.get(key, 0))
            # skip text already claimed: by anyone at exactly this span, or by this same entity anywhere around it
            # ("Priya" inside "Priya Shah"); other entities may nest ("his" inside "his mother")
            while i >= 0 and ((us_s + i, us_s + i + len(mtext)) in taken or
                              any(a < us_s + i + len(mtext) and us_s + i < b for a, b in ((m.start, m.end) for m in ent.mentions))):
                nxt = _find(utext, mtext, i + 1)
                i = nxt if nxt > i else -1
            if i < 0:
                out.dropped += 1
                continue
            s, e = us_s + i, us_s + i + len(mtext)
            taken.add((s, e))
            cursors[key] = i + len(mtext)
            ent.mentions.append(Mention(s, e, text[s:e], u, is_reference(mtext) and etype in ("PERSON", "ORG")))
        if ent.mentions:
            out.entities.append(ent)
    ids = {e.id for e in out.entities}
    for e in out.entities:
        if e.owner and e.owner != UNKNOWN and e.owner not in ids:
            e.owner = UNKNOWN
    for r in rels:
        if isinstance(r, list) and len(r) == 3 and all(isinstance(x, str) for x in r):
            a, rel, b = r[0].upper(), r[1].upper(), r[2].upper()
            if rel in RELATIONS and a in ids and b in ids and a != b:
                out.relations.append((a, rel, b))
    return out


# -- registry and masking ---------------------------------------------------------------------

def _norm(v: str) -> str:
    return re.sub(r"[\s\-./,]+", "", v).lower()


class Registry:
    """Stable placeholders across documents in one chat: the same value or name gets the same label."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], str] = {}
        self.counts: dict[str, int] = {}
        self.records: dict[str, dict] = {}

    def label_for(self, ent: Entity) -> str:
        names = [m.text for m in ent.mentions if not m.reference]
        base = ent.role if ent.type == "AMOUNT" and ent.role and ent.role != "OTHER" else ent.type
        keys = [(ent.type, _norm(n)) for n in names]
        for k in keys:
            if k in self.by_key:
                label = self.by_key[k]
                break
        else:
            self.counts[base] = self.counts.get(base, 0) + 1
            label = f"{base}_{self.counts[base]}"
            self.records[label] = {"type": ent.type, "role": ent.role, "subtype": ent.subtype, "values": []}
        for k, n in zip(keys, names):
            self.by_key.setdefault(k, label)
            if n not in self.records[label]["values"]:
                self.records[label]["values"].append(n)
        return label


def mask(res: Resolution, registry: Registry | None = None) -> dict:
    """Masked text plus the identity table. References stay as written; everything else is replaced."""
    reg = registry or Registry()
    labels = {e.id: reg.label_for(e) for e in res.entities if any(not m.reference for m in e.mentions)}
    spans = sorted(((m.start, m.end, labels[e.id]) for e in res.entities if e.id in labels for m in e.mentions
                    if not m.reference), key=lambda x: (x[0], -x[1]))
    out, cursor = [], 0
    for s, e, label in spans:
        if s < cursor:  # overlapping mention: the earlier, longer one already covers it
            continue
        out += [res.text[cursor:s], f"<{label}>"]
        cursor = e
    out.append(res.text[cursor:])
    table = []
    for e in res.entities:
        if e.id not in labels:
            continue
        table.append({"placeholder": labels[e.id], "type": e.type, "role": e.role, "subtype": e.subtype,
                      "owner": labels.get(e.owner, e.owner) if e.owner else None,
                      "values": reg.records[labels[e.id]]["values"],
                      "references": [m.text for m in e.mentions if m.reference]})
    rels = [[labels.get(a, a), r, labels.get(b, b)] for a, r, b in res.relations]
    return {"masked": "".join(out), "entities": table, "relations": rels}


# -- gold format and targets ------------------------------------------------------------------

def target_json(text: str, gold: dict) -> str:
    """The training target for a gold document: the contract JSON, mentions as [unit, text]."""
    us = units(text)

    def unit_of(s: int) -> int:
        for i, (a, b) in enumerate(us, 1):
            if a <= s < b:
                return i
        raise ValueError(f"offset {s} is outside every unit")

    ents = []
    for e in gold["entities"]:
        item = {"id": e["id"], "type": e["type"]}
        for k in ("role", "subtype", "owner"):
            if e.get(k):
                item[k] = e[k]
        item["mentions"] = [[unit_of(s), text[s:t]] for s, t in e["mentions"]]
        ents.append(item)
    return json.dumps({"entities": ents, "relations": gold.get("relations", [])}, ensure_ascii=False)


# -- scoring ----------------------------------------------------------------------------------

_TITLE_PREFIX = re.compile(r"(?:(?:Mr|Mrs|Ms|Mx|Dr|Prof|Judge|Justice|Lord|Lady|Sir|Dame)\.?\s+)+")


def _f1(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "tp": tp, "fp": fp, "fn": fn}


def score_doc(gold: dict, res: Resolution | None, relaxed: bool = False) -> dict:
    """Compare one prediction with gold. Gold mentions are (start, end) pairs.

    relaxed: a predicted mention matches the gold mention it overlaps most (for real text whose gold spans
    differ in edges, e.g. TAB includes "Mr" in names), instead of needing identical offsets."""
    text = gold["text"]
    g_ent = gold["entities"]
    g_of = {}  # (s, e) -> gold entity index
    for gi, e in enumerate(g_ent):
        for s, t in e["mentions"]:
            g_of[(s, t)] = gi
    p_ent = res.entities if res else []
    p_of = {(m.start, m.end): pi for pi, e in enumerate(p_ent) for m in e.mentions}
    if relaxed:  # re-key each predicted mention onto the gold span it overlaps most
        rekeyed, used = {}, set()
        for (ps, pe), pi in sorted(p_of.items()):
            best = max(((min(pe, gt) - max(ps, gs), (gs, gt)) for gs, gt in g_of if gs < pe and ps < gt and (gs, gt) not in used),
                       default=None)
            key = best[1] if best and best[0] > 0 else (ps, pe)
            used.add(key)
            rekeyed[key] = pi
        p_of = rekeyed

    # leaks: gold names and values (not references) whose characters no predicted name/value covers
    covered = [False] * len(text)
    for e in p_ent:
        for m in e.mentions:
            if not m.reference:
                for i in range(m.start, m.end):
                    covered[i] = True
    leaks = {"all": [0, 0], "core": [0, 0], "person": [0, 0]}
    no_mask = {tuple(x) for x in gold.get("no_mask", [])}  # gold says these needn't be hidden (TAB's NO_MASK)
    for e in g_ent:
        for s, t in e["mentions"]:
            if is_reference(text[s:t]) and e["type"] in ("PERSON", "ORG") or (s, t) in no_mask:
                continue
            if relaxed:  # a leading title ("Mr", "Judge") isn't identifying: only the rest must be masked
                m = _TITLE_PREFIX.match(text, s, t)
                s = m.end() if m and m.end() < t else s
            leaked = not all(covered[i] for i in range(s, t) if text[i].isalnum())
            for k in ("all",) + (("core",) if e["type"] in CORE_TYPES else ()) + (("person",) if e["type"] == "PERSON" else ()):
                leaks[k][0] += leaked
                leaks[k][1] += 1

    # mention detection (exact offsets, references included)
    matched = set(g_of) & set(p_of)
    mention = (len(matched), len(p_of) - len(matched), len(g_of) - len(matched))

    # coreference: pairwise links among matched mentions
    ms = sorted(matched)
    tp = fp = fn = 0
    for i in range(len(ms)):
        for j in range(i + 1, len(ms)):
            g_same = g_of[ms[i]] == g_of[ms[j]]
            p_same = p_of[ms[i]] == p_of[ms[j]]
            tp += g_same and p_same
            fp += p_same and not g_same
            fn += g_same and not p_same
    # links the model missed because it never found a mention also count as missed
    for gi, e in enumerate(g_ent):
        n_all, n_hit = len(e["mentions"]), sum(1 for m in e["mentions"] if tuple(m) in matched)
        fn += n_all * (n_all - 1) // 2 - n_hit * (n_hit - 1) // 2

    # alignment: each gold entity -> the predicted entity holding most of its mentions
    align: dict[int, int] = {}
    for gi, e in enumerate(g_ent):
        votes: dict[int, int] = {}
        for m in e["mentions"]:
            pi = p_of.get(tuple(m))
            if pi is None:  # partial overlap still counts for alignment
                pi = next((p_of[k] for k in p_of if k[0] < m[1] and m[0] < k[1]), None)
            if pi is not None:
                votes[pi] = votes.get(pi, 0) + 1
        if votes:
            align[gi] = max(votes, key=votes.get)
    p_to_g = {}
    for gi, pi in align.items():
        p_to_g.setdefault(pi, gi)
    gid = {e["id"]: gi for gi, e in enumerate(g_ent)}
    pid = {e.id: pi for pi, e in enumerate(p_ent)}

    owner = {"correct": 0, "total": 0, "unknown_total": 0, "unknown_correct": 0}
    types = {"correct": 0, "total": 0}
    roles = {"correct": 0, "total": 0}
    for gi, e in enumerate(g_ent):
        pe = p_ent[align[gi]] if gi in align else None
        types["total"] += 1
        types["correct"] += bool(pe and pe.type == e["type"])
        if e["type"] == "AMOUNT":
            roles["total"] += 1
            roles["correct"] += bool(pe and pe.role == e.get("role"))
        if e["type"] in OWNED_TYPES and e.get("owner"):
            owner["total"] += 1
            want = e["owner"]
            got = None
            if pe and pe.owner:
                got = UNKNOWN if pe.owner == UNKNOWN else (g_ent[p_to_g[pid[pe.owner]]]["id"]
                                                          if pid.get(pe.owner) in p_to_g else "?")
            ok = got == want
            owner["correct"] += ok
            if want == UNKNOWN:
                owner["unknown_total"] += 1
                owner["unknown_correct"] += ok

    g_rel = {tuple(r) for r in gold.get("relations", [])}
    p_rel = set()
    for a, r, b in (res.relations if res else []):
        if pid.get(a) in p_to_g and pid.get(b) in p_to_g:
            p_rel.add((g_ent[p_to_g[pid[a]]]["id"], r, g_ent[p_to_g[pid[b]]]["id"]))
        else:
            p_rel.add((a, r, b + "?"))
    rel = (len(g_rel & p_rel), len(p_rel - g_rel), len(g_rel - p_rel))

    # identity consistency: a gold person whose names all landed in ONE predicted entity, holding no one else
    persons = [gi for gi, e in enumerate(g_ent) if e["type"] == "PERSON"]
    resolved = 0
    for gi in persons:
        names = [tuple(m) for m in g_ent[gi]["mentions"] if not is_reference(text[m[0]:m[1]])]
        pis = {p_of.get(m) for m in names}
        if len(pis) == 1 and None not in pis:
            pi = pis.pop()
            others = {g_of.get((m.start, m.end)) for m in p_ent[pi].mentions} - {gi, None}
            resolved += not others
    return {"valid": bool(res and res.valid), "leaks": leaks, "mention": mention, "coref": (tp, fp, fn),
            "owner": owner, "types": types, "roles": roles, "relations": rel,
            "persons": [resolved, len(persons)], "dropped": res.dropped if res else 0}


def aggregate(per_doc: list[dict]) -> dict:
    def tot(path):
        acc = None
        for d in per_doc:
            v = d
            for k in path:
                v = v[k]
            acc = list(v) if acc is None else [a + b for a, b in zip(acc, v)]
        return acc or [0, 0, 0]

    def ratio(key, num="correct", den="total"):
        n = sum(d[key][num] for d in per_doc)
        t = sum(d[key][den] for d in per_doc)
        return n / t if t else None

    leak_all, leak_core = tot(("leaks", "all")), tot(("leaks", "core"))
    leak_person = tot(("leaks", "person"))
    persons = tot(("persons",))
    return {
        "docs": len(per_doc),
        "valid": sum(d["valid"] for d in per_doc) / max(len(per_doc), 1),
        "leak": leak_all[0] / leak_all[1] if leak_all[1] else 0.0,
        "core_leak": leak_core[0] / leak_core[1] if leak_core[1] else 0.0,
        "person_leak": leak_person[0] / leak_person[1] if leak_person[1] else 0.0,
        "mention": _f1(*tot(("mention",))),
        "coref": _f1(*tot(("coref",))),
        "owner_acc": ratio("owner"),
        "unknown_acc": ratio("owner", "unknown_correct", "unknown_total"),
        "type_acc": ratio("types"),
        "amount_role_acc": ratio("roles"),
        "relations": _f1(*tot(("relations",))),
        "persons_resolved": persons[0] / persons[1] if persons[1] else None,
        "dropped_mentions": sum(d["dropped"] for d in per_doc),
    }


# -- the app's analyzer -----------------------------------------------------------------------

# -- classify mode: document categories and category-specific extras ----------------------------

CATEGORIES = ["medical", "legal", "mergers_acquisitions", "banking_finance", "hr", "insurance", "real_estate",
              "education", "code", "general"]
CLASSIFY_PROMPT = """Classify this document for a privacy gateway and find category-specific private details.
Categories: {cats}. A document can have more than one.

"extras": exact text of private details the document's categories make sensitive that are NOT names,
organisations, addresses, phone numbers, emails, ID numbers, money amounts or dates. For example:
medications and doses, vital signs, test results, diagnoses and procedures (medical); case or matter
numbers, charges and allegations (legal); project codenames, valuations and deal terms (mergers);
performance ratings, disciplinary findings and resignation reasons (hr); hostnames, internal URLs and
access tokens (code). Copy each one exactly as written. Only values, never field labels like "Age" or "MRN".

Return ONE JSON object and nothing else:
{{"categories": ["..."], "summary": "one sentence", "extras": [{{"text": "...", "category": "..."}}]}}

{doc}"""
# field labels and filler a classifier sometimes returns as "values"
_LABEL_WORDS = {"age", "dob", "date of birth", "mrn", "employee id", "name", "address", "phone", "email", "pan",
                "aadhaar", "salary", "id", "date", "height", "weight", "gender", "diagnosis", "blood group",
                "medical record number", "policy number", "account number", "contact number"}


def categories_from_resolution(res: Resolution) -> set[str]:
    """Categories inferred in code from what the fill found (subtypes, roles, relations)."""
    subs = {e.subtype for e in res.entities if e.subtype}
    roles = {e.role for e in res.entities if e.role}
    rels = {r for _, r, _ in res.relations}
    types = {e.type for e in res.entities}
    cats = set()
    if subs & {"HEALTH", "MEDICAL_RECORD", "BODY_MEASUREMENT", "DISABILITY"} or "TREATS" in rels:
        cats.add("medical")
    if "SALARY" in roles or "EMPLOYEE_ID" in subs or "MANAGES" in rels:
        cats.add("hr")
    if roles & {"DEAL_VALUE", "REVENUE"} or "PROJECT" in types:
        cats.add("mergers_acquisitions")
    if "LOAN" in roles or subs & {"BANK_ACCOUNT", "IFSC", "CARD"} or "GUARANTOR_FOR" in rels:
        cats.add("banking_finance")
    if "POLICY" in subs or "NOMINEE_OF" in rels:
        cats.add("insurance")
    if rels & {"REPRESENTS", "CLIENT_OF"}:
        cats.add("legal")
    if "LANDLORD_OF" in rels:
        cats.add("real_estate")
    if "SECRET" in types:
        cats.add("code")
    return cats


def keep_extra(text: str) -> bool:
    """Drop labels, verbs and fragments the classifier sometimes returns as private details."""
    t = text.strip().lower().strip(".,:;")
    if len(t) < 3 or t in _LABEL_WORDS or t in _REFERENCE_WORDS:
        return False
    words = t.split()
    return not (len(words) == 1 and t.isalpha() and (t.endswith("ed") or t.endswith("ing")))


class ResolutionAnalyzer:
    """Call 1 with an entity-resolution model (e.g. Glimmer + er-v2a LoRA) behind the app's Masker.

    One call per message or document instead of one per paragraph, so every mention of a person in it
    shares one identity. Each name or value becomes a Span whose `canonical` is the entity's fullest
    name, so the vault gives "Rohan Majji", "Rohan" and "Mr. Majji" one placeholder; `owner` and the
    relations become vault edges. References (he, his, the employee) aren't masked. No context blocks:
    this model wasn't trained on them.
    """

    name = "glimmer-resolution"

    def __init__(self, chat_backend):
        import os
        self.chat, self.model = chat_backend, chat_backend.model
        # MUSE_SHIELD_ER_PROMPT=v3 gives a model that wasn't trained on it (Muse Spark, base Glimmer) the same v3
        # instructions as er-v3, for like-for-like benchmarks; MUSE_SHIELD_ER_EXAMPLE=1 adds the worked example for a
        # model that wasn't fine-tuned on the contract. The app's fine-tunes run without it (they were trained so).
        self.version = os.environ.get("MUSE_SHIELD_ER_PROMPT") or prompt_version(self.model)
        self.example = os.environ.get("MUSE_SHIELD_ER_EXAMPLE") == "1"

    def _call(self, text: str):
        msgs, usage, err = messages(text, example=self.example, version=self.version), {"prompt_tokens": 0, "completion_tokens": 0}, ""
        for attempt in (1, 2):
            raw, u = self.chat._call(msgs)
            for k in usage:
                usage[k] += u.get(k, 0)
            try:
                return parse(raw, text), usage, attempt, ""
            except ContractError as exc:
                err = str(exc)
                msgs = msgs + [{"role": "assistant", "content": raw},
                               {"role": "user", "content": f"That output broke the contract ({err}). Reply with only the corrected JSON object."}]
        return None, usage, 2, err

    def classify_document(self, text: str) -> dict:
        """Classify mode: categories, a one-line summary and category-specific extras, from the same model."""
        msg = [{"role": "user", "content": CLASSIFY_PROMPT.format(cats=", ".join(CATEGORIES), doc=text)}]
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        try:
            raw, u = self.chat._call(msg)
            for k in usage:
                usage[k] += u.get(k, 0)
            data = _loads(raw)
        except Exception as exc:  # noqa: BLE001 - classify is best effort: the fill still masks
            return {"categories": [], "summary": "", "extras": [], "usage": usage, "error": f"{exc!s:.120}"}
        cats = [c for c in (str(x).lower() for x in data.get("categories") or []) if c in CATEGORIES]
        extras = []
        for x in data.get("extras") or []:
            if isinstance(x, dict) and isinstance(x.get("text"), str) and keep_extra(x["text"]) and x["text"] in text:
                extras.append({"text": x["text"].strip(), "category": str(x.get("category", "")).lower()})
        return {"categories": cats, "summary": str(data.get("summary") or "")[:300], "extras": extras, "usage": usage, "error": ""}

    def analyze_document(self, text: str, paras: list[tuple[int, str]]):
        from muse_shield.analysis import Analysis, Span, split_sentences
        import time as _time
        t0 = _time.perf_counter()
        res, usage, attempts, err = self._call(text)
        out = [Analysis(p, split_sentences(p) or [p]) for _, p in paras]
        if res is None:
            out[0].valid, out[0].error = False, err
        else:
            ident = {}
            for e in res.entities:
                names = [m.text for m in e.mentions if not m.reference]
                if names:
                    ident[e.id] = (e.type, max(names, key=len))
            for e in res.entities:
                if e.id not in ident:
                    continue
                owner = ident.get(e.owner) if e.owner and e.owner != UNKNOWN else None
                role = e.role if e.type == "AMOUNT" else None
                for m in e.mentions:
                    if m.reference:
                        continue
                    for (off, p), a in zip(paras, out):
                        if off <= m.start and m.end <= off + len(p):
                            a.entities.append(Span(m.text, e.type, m.start - off, m.end - off, role,
                                                   canonical=ident[e.id][1], owner=owner))
                            break
            out[0].relations = [(ident[a], r, ident[b]) for a, r, b in res.relations if a in ident and b in ident]
            out[0].categories = sorted(categories_from_resolution(res))
        out[0].usage, out[0].attempts, out[0].latency_ms = usage, attempts, (_time.perf_counter() - t0) * 1000
        return out

    def analyze(self, paragraphs: list[str], known_labels=None):
        return [self.analyze_document(p, [(0, p)])[0] for p in paragraphs]
