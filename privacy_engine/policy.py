"""Privacy policy: classify each entity as PII / CONFIDENTIAL / PUBLIC and pick an action.

Sensitivity is contextual. "Meta" in "what did Meta ship at Connect?" is public;
the same word in "we're acquiring Meta's AR unit" is deal intel. Money is the
same: "$20 for lunch" is public, "$1.2B offer" is confidential.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

from .detector.rules import PUBLIC_ORGS
from .entities import Detection, Entity, EntityType, Sensitivity
from .values import parse_money


class Action(str, Enum):
    MASK = "mask"
    BLOCK = "block"
    ALLOW = "allow"


DEFAULT_CLASSIFICATION: dict[EntityType, Sensitivity] = {
    EntityType.PERSON: Sensitivity.PII,
    EntityType.EMAIL: Sensitivity.PII,
    EntityType.PHONE: Sensitivity.PII,
    EntityType.SSN: Sensitivity.PII,
    EntityType.CREDIT_CARD: Sensitivity.PII,
    EntityType.IBAN: Sensitivity.PII,
    EntityType.ADDRESS: Sensitivity.PII,
    EntityType.IP_ADDRESS: Sensitivity.PII,
    EntityType.API_KEY: Sensitivity.CONFIDENTIAL,
    EntityType.PROJECT: Sensitivity.CONFIDENTIAL,
    EntityType.CONFIDENTIAL_TERM: Sensitivity.CONFIDENTIAL,
    EntityType.ORG: Sensitivity.CONFIDENTIAL,  # well-known public orgs are relaxed below
    EntityType.MONEY: Sensitivity.PUBLIC,  # escalated by size or confidential context
    EntityType.LOCATION: Sensitivity.PUBLIC,
}


@dataclass
class Policy:
    name: str = "default"
    version: int = 1
    classification: dict[EntityType, Sensitivity] = field(default_factory=lambda: dict(DEFAULT_CLASSIFICATION))
    actions: dict[Sensitivity, Action] = field(
        default_factory=lambda: {
            Sensitivity.PII: Action.MASK,
            Sensitivity.CONFIDENTIAL: Action.MASK,
            Sensitivity.PUBLIC: Action.ALLOW,
        }
    )
    # Per-type override that beats the sensitivity-level action (e.g. BLOCK on SSN).
    type_actions: dict[EntityType, Action] = field(default_factory=dict)
    # PUBLIC types that become CONFIDENTIAL when the passage is confidential.
    escalate_in_confidential: list[EntityType] = field(
        default_factory=lambda: [EntityType.ORG, EntityType.MONEY, EntityType.LOCATION]
    )
    money_threshold: float = 1_000_000.0
    public_orgs: list[str] = field(default_factory=lambda: sorted(PUBLIC_ORGS))
    allow_terms: list[str] = field(default_factory=lambda: ["Llama", "Meta AI"])
    terms: dict[str, EntityType] = field(default_factory=dict)  # taught: term -> type
    cues: list[str] = field(default_factory=list)  # taught confidential-context cues
    use_llm: bool = True

    # -- serialization -------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["classification"] = {k.value: v.value for k, v in self.classification.items()}
        d["actions"] = {k.value: v.value for k, v in self.actions.items()}
        d["type_actions"] = {k.value: v.value for k, v in self.type_actions.items()}
        d["escalate_in_confidential"] = [t.value for t in self.escalate_in_confidential]
        d["terms"] = {k: v.value for k, v in self.terms.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Policy":
        base = cls()
        return cls(
            name=d.get("name", base.name),
            version=int(d.get("version", base.version)),
            classification={
                **base.classification,
                **{EntityType(k): Sensitivity(v) for k, v in d.get("classification", {}).items()},
            },
            actions={**base.actions, **{Sensitivity(k): Action(v) for k, v in d.get("actions", {}).items()}},
            type_actions={EntityType(k): Action(v) for k, v in d.get("type_actions", {}).items()},
            escalate_in_confidential=[
                EntityType(t) for t in d.get("escalate_in_confidential", [t.value for t in base.escalate_in_confidential])
            ],
            money_threshold=float(d.get("money_threshold", base.money_threshold)),
            public_orgs=list(d.get("public_orgs", base.public_orgs)),
            allow_terms=list(d.get("allow_terms", base.allow_terms)),
            terms={k: EntityType(v) for k, v in d.get("terms", {}).items()},
            cues=list(d.get("cues", [])),
            use_llm=bool(d.get("use_llm", True)),
        )

    def copy(self) -> "Policy":
        return Policy.from_dict(self.to_dict())


@dataclass
class Decision:
    entity: Entity
    sensitivity: Sensitivity
    action: Action
    reason: str

    def to_dict(self) -> dict:
        return {
            **self.entity.to_dict(),
            "sensitivity": self.sensitivity.value,
            "action": self.action.value,
            "reason": self.reason,
        }


@dataclass
class PolicyResult:
    decisions: list[Decision]
    confidential_context: bool

    @property
    def blocked(self) -> list[Decision]:
        return [d for d in self.decisions if d.action is Action.BLOCK]

    @property
    def to_mask(self) -> list[Decision]:
        return [d for d in self.decisions if d.action is Action.MASK]

    def to_dict(self) -> dict:
        return {
            "confidential_context": self.confidential_context,
            "decisions": [d.to_dict() for d in self.decisions],
            "blocked": bool(self.blocked),
        }


def classify(entity: Entity, policy: Policy, confidential_context: bool) -> tuple[Sensitivity, str]:
    lowered = entity.text.lower()
    if any(lowered == t.lower() for t in policy.allow_terms):
        return Sensitivity.PUBLIC, "on allowlist"
    if entity.source == "custom":
        return policy.classification.get(entity.type, Sensitivity.CONFIDENTIAL), "taught term"

    base = policy.classification.get(entity.type, Sensitivity.CONFIDENTIAL)
    reason = f"{entity.type.value} is {base.value} by default"

    if entity.type is EntityType.ORG and lowered in {o.lower() for o in policy.public_orgs}:
        base, reason = Sensitivity.PUBLIC, "well-known public company"

    if entity.type is EntityType.MONEY:
        amount = parse_money(entity.text)
        if amount is not None and amount >= policy.money_threshold:
            return Sensitivity.CONFIDENTIAL, f"amount ≥ {policy.money_threshold:,.0f}"

    if base is Sensitivity.PUBLIC and confidential_context and entity.type in policy.escalate_in_confidential:
        return Sensitivity.CONFIDENTIAL, "escalated: confidential context"
    return base, reason


def evaluate(detection: Detection, policy: Policy) -> PolicyResult:
    decisions = []
    for e in detection.entities:
        sensitivity, reason = classify(e, policy, detection.context.confidential)
        action = policy.type_actions.get(e.type) or policy.actions[sensitivity]
        decisions.append(Decision(e, sensitivity, action, reason))
    return PolicyResult(decisions, detection.context.confidential)

