"""Teach -> Test -> Deploy: personalize the policy without breaking it.

Teach   edits a *draft* policy: taught sensitive terms ("Bluebird" is a project),
        always-public terms, confidential-context cues, and example sentences.
Test    runs the draft and the active policy side by side over regression cases
        plus the user's own examples, and reports what got fixed or regressed.
Deploy  promotes the draft to a new active version (refusing on regressions
        unless forced) and keeps history for one-click rollback.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .entities import EntityType
from .masking import MaskResult
from .policy import Policy


@dataclass
class TestCase:
    text: str
    must_mask: list[str] = field(default_factory=list)
    must_keep: list[str] = field(default_factory=list)
    source: str = "builtin"

    def check(self, masked: str) -> tuple[bool, list[str]]:
        problems = [f"leaked {s!r}" for s in self.must_mask if s.lower() in masked.lower()]
        problems += [f"over-masked {s!r}" for s in self.must_keep if s not in masked]
        return not problems, problems


BUILTIN_CASES = [
    TestCase("Draft an email to Sarah Chen about the $1.2B offer.", ["Sarah Chen", "$1.2B"]),
    TestCase("My SSN is 123-45-6789 and card 4111 1111 1111 1111.", ["123-45-6789", "4111 1111 1111 1111"]),
    TestCase("Reach me at priya@northwind.io or (415) 555-0134.", ["priya@northwind.io", "555-0134"]),
    TestCase("What did Meta announce at Connect?", [], ["Meta", "Connect"]),
    TestCase("Explain how Llama models handle long context.", [], ["Llama"]),
    TestCase("Confidential: we are acquiring Meta's AR unit.", ["Meta"]),
    TestCase("Project Falcon launches with Northwind Capital.", ["Project Falcon", "Northwind Capital"]),
    TestCase("I paid $20 for lunch, is that a lot?", [], ["$20"]),
]


@dataclass
class CaseResult:
    text: str
    source: str
    active_pass: bool
    draft_pass: bool
    active_masked: str
    draft_masked: str
    problems: list[str]

    @property
    def status(self) -> str:
        if self.active_pass == self.draft_pass:
            return "pass" if self.draft_pass else "fail"
        return "fixed" if self.draft_pass else "regressed"


@dataclass
class TestReport:
    cases: list[CaseResult]

    def count(self, status: str) -> int:
        return sum(c.status == status for c in self.cases)

    @property
    def regressions(self) -> int:
        return self.count("regressed")

    def to_dict(self) -> dict:
        return {
            "summary": {s: self.count(s) for s in ("pass", "fixed", "regressed", "fail")},
            "draft_pass_rate": sum(c.draft_pass for c in self.cases) / max(len(self.cases), 1),
            "active_pass_rate": sum(c.active_pass for c in self.cases) / max(len(self.cases), 1),
            "cases": [{**asdict(c), "status": c.status} for c in self.cases],
        }


class DeployBlocked(RuntimeError):
    pass


class PolicyStore:
    """Active policy, an optional draft, version history and user examples, as one JSON file."""

    def __init__(self, path: Path):
        self.path = path
        self.active = Policy()
        self.draft: Policy | None = None
        self.history: list[Policy] = []
        self.examples: list[TestCase] = []
        if path.exists():
            data = json.loads(path.read_text())
            self.active = Policy.from_dict(data["active"])
            self.draft = Policy.from_dict(data["draft"]) if data.get("draft") else None
            self.history = [Policy.from_dict(p) for p in data.get("history", [])]
            self.examples = [TestCase(**e) for e in data.get("examples", [])]

    def save(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "active": self.active.to_dict(),
                    "draft": self.draft.to_dict() if self.draft else None,
                    "history": [p.to_dict() for p in self.history[-20:]],
                    "examples": [asdict(e) for e in self.examples],
                },
                indent=2,
            )
        )

    # -- teach ---------------------------------------------------------------
    def ensure_draft(self) -> Policy:
        if self.draft is None:
            self.draft = self.active.copy()
            self.draft.version = self.active.version + 1
        return self.draft

    def teach_term(self, term: str, etype: EntityType) -> Policy:
        d = self.ensure_draft()
        d.terms[term.strip()] = etype
        d.allow_terms = [t for t in d.allow_terms if t.lower() != term.strip().lower()]
        return d

    def teach_public(self, term: str) -> Policy:
        d = self.ensure_draft()
        if term.strip().lower() not in {t.lower() for t in d.allow_terms}:
            d.allow_terms.append(term.strip())
        d.terms = {k: v for k, v in d.terms.items() if k.lower() != term.strip().lower()}
        return d

    def teach_cue(self, cue: str) -> Policy:
        d = self.ensure_draft()
        if cue.strip() and cue.strip() not in d.cues:
            d.cues.append(cue.strip())
        return d

    def teach_example(self, text: str, must_mask: list[str], must_keep: list[str], etype: EntityType | None = None) -> Policy:
        """Record a test case; with etype, also teach each must_mask span as a term."""
        self.examples.append(TestCase(text, must_mask, must_keep, source="taught"))
        d = self.ensure_draft()
        if etype is not None:
            for span in must_mask:
                self.teach_term(span, etype)
        for span in must_keep:
            self.teach_public(span)
        return d

    def discard_draft(self) -> None:
        self.draft = None

    def diff(self) -> dict:
        if self.draft is None:
            return {}
        a, d = self.active.to_dict(), self.draft.to_dict()
        return {k: {"active": a[k], "draft": d[k]} for k in d if k != "version" and a.get(k) != d[k]}

    # -- test ----------------------------------------------------------------
    def test(self, mask_with: Callable[[str, Policy], MaskResult]) -> TestReport:
        draft = self.draft or self.active
        results = []
        for case in [*BUILTIN_CASES, *self.examples]:
            a = mask_with(case.text, self.active).masked
            d = mask_with(case.text, draft).masked
            a_ok, _ = case.check(a)
            d_ok, problems = case.check(d)
            results.append(CaseResult(case.text, case.source, a_ok, d_ok, a, d, problems))
        return TestReport(results)

    # -- deploy --------------------------------------------------------------
    def deploy(self, report: TestReport | None = None, force: bool = False) -> Policy:
        if self.draft is None:
            raise DeployBlocked("nothing to deploy: no draft")
        if report is not None and report.regressions and not force:
            raise DeployBlocked(f"{report.regressions} regression(s); fix them or deploy with force")
        self.history.append(self.active)
        self.active, self.draft = self.draft, None
        self.save()
        return self.active

    def rollback(self) -> Policy:
        if not self.history:
            raise DeployBlocked("no earlier version to roll back to")
        # Restores the previous version under a new number, so versions stay monotonic
        # and repeated rollbacks keep walking back through history.
        rolled = self.history.pop().copy()
        rolled.version = self.active.version + 1
        self.active = rolled
        self.save()
        return self.active

    def set_active(self, policy: Policy) -> Policy:
        """Direct edit from the policy editor: still versioned, still rollback-able."""
        policy.version = self.active.version + 1
        self.history.append(self.active)
        self.active = policy
        self.save()
        return self.active
