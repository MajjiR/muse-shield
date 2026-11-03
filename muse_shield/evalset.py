"""Synthetic labeled eval set for the analyze() contract. Fake people and places only.

Each case is built from a list of sentences, so gold context sentence numbers
are exact. Gold entities are (text, type, role) and must occur verbatim.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

PEOPLE = ["Rohan", "Priya Shah", "Ananya Iyer", "Vikram Rao", "Sonia Mehta", "Arjun Nair", "Kavya Reddy",
          "Farhan Qureshi", "Meera Pillai", "Daniel Okafor", "Lucia Fernandes", "Ishaan Kapoor"]
ORGS = ["Northwind", "Kestrel Labs", "Brightline Finance", "Oakmont Retail", "Tidewater Logistics", "Halcyon Health"]
BANKS = ["Coastal Bank", "Sahyadri Co-operative Bank", "Unity Finance"]
CITIES = ["Visakhapatnam", "Pune", "Kochi", "Indore", "Mysuru", "Nagpur"]
ADDRESSES = ["12-4, MVP Colony, Visakhapatnam", "Flat 302, Lake View Apartments, Kochi",
             "45 Gandhi Road, Indore", "Plot 7, Sector 21, Nagpur"]
CODENAMES = ["Project Kingfisher", "Project Monsoon", "Project Banyan"]
SALARIES = ["10 lakh rupees", "18 lakh rupees", "₹24 lakh a year", "12 LPA"]
PRICES = ["₹45,000", "₹3.2 lakh", "6,50,000 rupees"]
LOANS = ["25 lakh", "₹40 lakh", "8 lakh rupees"]
DEALS = ["₹120 crore", "$1.2B", "₹45 crore"]
BUDGETS = ["₹2 crore", "15 lakh rupees", "₹60 lakh"]


@dataclass(frozen=True)
class Pools:
    """Fillers for the templates. Training uses a disjoint set so evals measure generalization."""

    people: list[str]
    orgs: list[str]
    banks: list[str]
    cities: list[str]
    addresses: list[str]
    codenames: list[str]
    salaries: list[str]
    prices: list[str]
    loans: list[str]
    deals: list[str]
    budgets: list[str]


EVAL_POOLS = Pools(PEOPLE, ORGS, BANKS, CITIES, ADDRESSES, CODENAMES, SALARIES, PRICES, LOANS, DEALS, BUDGETS)


@dataclass
class GoldEntity:
    text: str
    type: str
    role: str | None = None


@dataclass
class GoldContext:
    sentences: list[int]
    kind: str


@dataclass
class Case:
    id: str
    template: str
    sentences: list[str]
    entities: list[GoldEntity] = field(default_factory=list)
    contexts: list[GoldContext] = field(default_factory=list)

    @property
    def paragraph(self) -> str:
        return " ".join(self.sentences)


def _templates(rng: random.Random, pools: Pools):
    p = lambda: rng.choice(pools.people)  # noqa: E731
    pick = rng.choice

    def acceptance():
        name, sal, addr = "Rohan", "10 lakh rupees", "12-4, MVP Colony, Visakhapatnam"
        return ("acceptance", [f"My name is {name} and I earn {sal}.", f"Tomorrow I'm planning to buy a land at {addr}."],
                [GoldEntity(name, "PERSON"), GoldEntity(sal, "AMOUNT", "SALARY"), GoldEntity(addr, "ADDRESS")],
                [GoldContext([2], "DECISION")])

    def salary_decision():
        name, sal, addr = p(), pick(pools.salaries), pick(pools.addresses)
        return ("salary_decision", [f"My name is {name} and I earn {sal}.", f"Next month I'm planning to buy a flat at {addr}."],
                [GoldEntity(name, "PERSON"), GoldEntity(sal, "AMOUNT", "SALARY"), GoldEntity(addr, "ADDRESS")],
                [GoldContext([2], "DECISION")])

    def deal():
        a, b = rng.sample(pools.orgs, 2)
        val, lead = pick(pools.deals), p()
        return ("deal", [f"{a} has agreed to acquire {b} for {val}.", f"{lead} is leading the due diligence."],
                [GoldEntity(a, "ORG"), GoldEntity(b, "ORG"), GoldEntity(val, "AMOUNT", "DEAL_VALUE"), GoldEntity(lead, "PERSON")],
                [GoldContext([1, 2], "DEAL")])

    def negotiation():
        name = p()
        s1, s2 = rng.sample(pools.salaries, 2)
        return ("negotiation", [f"We offered {name} a salary of {s1}.", f"They are asking for {s2} before they sign."],
                [GoldEntity(name, "PERSON"), GoldEntity(s1, "AMOUNT", "SALARY"), GoldEntity(s2, "AMOUNT", "SALARY")],
                [GoldContext([1, 2], "NEGOTIATION")])

    def hr():
        name, org = p(), pick(pools.orgs)
        return ("hr", [f"{name} from the {org} sales team is being let go at the end of the month.",
                       "Please keep this quiet until the announcement."],
                [GoldEntity(name, "PERSON"), GoldEntity(org, "ORG")],
                [GoldContext([1], "HR")])

    def project():
        code, city, budget = pick(pools.codenames), pick(pools.cities), pick(pools.budgets)
        return ("project", [f"{code} will launch in {city} in March.", f"The approved budget is {budget}."],
                [GoldEntity(code, "PROJECT"), GoldEntity(city, "LOCATION"), GoldEntity(budget, "AMOUNT", "BUDGET")],
                [GoldContext([1, 2], "PROJECT")])

    def loan():
        name, amt, bank = p(), pick(pools.loans), pick(pools.banks)
        return ("loan", [f"{name} took a home loan of {amt} from {bank} last year."],
                [GoldEntity(name, "PERSON"), GoldEntity(amt, "AMOUNT", "LOAN"), GoldEntity(bank, "ORG")], [])

    def price():
        name, amt = p(), pick(pools.prices)
        return ("price", [f"I bought a used scooter from {name} for {amt}."],
                [GoldEntity(name, "PERSON"), GoldEntity(amt, "AMOUNT", "PRICE")], [])

    def plan():
        city, org = pick(pools.cities), pick(pools.orgs)
        return ("plan", [f"Next quarter {org} plans to open a second office in {city}.", "Hiring starts in January."],
                [GoldEntity(org, "ORG"), GoldEntity(city, "LOCATION")],
                [GoldContext([1, 2], "PLAN")])

    def negative():
        text = pick(["How does a home loan EMI get calculated?", "What is a good way to learn Python?",
                     "Explain compound interest with a simple example.", "Write a haiku about the monsoon."])
        return ("negative", [text], [], [])

    return [acceptance, salary_decision, deal, negotiation, hr, project, loan, price, plan, negative]


def generate(n: int = 60, seed: int = 3, pools: Pools = EVAL_POOLS) -> list[Case]:
    rng = random.Random(seed)
    makers = _templates(rng, pools)
    cases = []
    for i in range(n):
        make = makers[0] if i == 0 else makers[1 + (i - 1) % (len(makers) - 1)]
        template, sentences, ents, ctxs = make()
        cases.append(Case(f"c{i:03d}", template, sentences, ents, ctxs))
    return cases
