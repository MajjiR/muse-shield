"""Two-agent demo: agents coordinate in placeholders; only the local executor ever sends real data.

    .venv/bin/python -m muse_shield.agent.demo

Offline and deterministic (no model calls), so it's reliable on stage. All data is invented.

1. The vault holds a deal: the people, amounts and contact are already masked.
2. research -> finance: "is <DEAL_VALUE_1> fair against <BUDGET_1>?", both amounts sealed to finance only.
3. finance opens the sealed values locally, decides, and answers in placeholders.
4. research gives the mail agent a single-use capability to email <PERSON_1>.
5. The mail agent redeems it through the executor; the user confirms; the email goes to the outbox.
6. Attacks: tampered envelope, replay, a third agent opening sealed values, a reused capability.
7. The audit chain verifies.
"""

from __future__ import annotations

import json
import os
import re

from ..app.vault import Vault
from .executor import Executor
from .protocol import AgentIdentity, Capabilities, Directory, Endpoint, ProtocolError, canonical, unseal

SEAL_POLICY = {("research", "finance"): {"AMOUNT"}}  # finance may see amounts, nothing else


def wire(env: dict) -> str:
    shown = {k: env[k] for k in ("from", "to", "body", "refs")}
    shown["sealed"] = [{"label": s["label"], "ct": s["ct"][:24] + "…"} for s in env["sealed"]]
    shown["caps"] = [c[:32] + "…" for c in env["caps"]]
    return json.dumps(shown, ensure_ascii=False, indent=2)


SCALE = {"thousand": 1e3, "k": 1e3, "lakh": 1e5, "lac": 1e5, "crore": 1e7, "cr": 1e7, "million": 1e6, "m": 1e6, "billion": 1e9, "b": 1e9}


def money(text: str) -> float:
    """'₹120 crore' -> 1.2e9, '$15 million' -> 1.5e7, '4,03,560' -> 403560 (finance's local arithmetic)."""
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]+)?", text)
    if not m:
        raise ValueError(f"not an amount: {text}")
    return float(m.group(1).replace(",", "")) * SCALE.get((m.group(2) or "").lower(), 1.0)


def run(verbose: bool = True) -> dict:
    say = print if verbose else (lambda *a, **k: None)
    vault = Vault(":memory:", master := os.urandom(32))
    chat = vault.create_chat()
    person, pid = vault.entity_placeholder(chat, "PERSON", "Priya Shah")
    _, eid = vault.entity_placeholder(chat, "CONTACT", "priya@kestrel.io")
    vault.link_entities(eid, pid, "identifies")
    org, _ = vault.entity_placeholder(chat, "ORG", "Kestrel Labs")
    price, _ = vault.entity_placeholder(chat, "AMOUNT", "₹120 crore", base="DEAL_VALUE")
    budget, _ = vault.entity_placeholder(chat, "AMOUNT", "₹100 crore", base="BUDGET")
    deal = vault.add_context(chat, "DEAL", "ACQUISITION", "Acme will acquire Kestrel Labs for ₹120 crore.",
                             f"Acme will acquire {org} for {price}.", "company acquisition")

    research, finance, mailer, eve = (AgentIdentity(n) for n in ("research", "finance", "mailer", "eve"))
    directory = Directory(research, finance, mailer, eve)
    ep = {i.name: Endpoint(i, directory, SEAL_POLICY) for i in (research, finance, mailer, eve)}
    caps = Capabilities.for_vault(master)
    executor = Executor(vault)
    log: dict = {"chat": chat}

    say("1 · research → finance (amounts sealed to finance only)")
    ask = ep["research"].build("finance", "deal-review", f"Is {price} a fair price for {deal}? Our budget is {budget}.",
                               vault=vault, chat_id=chat, seal_labels=[price, budget])
    say(wire(ask))
    log["ask_on_wire_has_values"] = "₹" in json.dumps(ask)

    say("\n2 · finance opens it locally and answers in placeholders")
    got = ep["finance"].open(ask)
    over = money(got["values"][price]) / money(got["values"][budget]) - 1
    verdict = f"{price} is {over:.0%} over {budget}. Recommend negotiating down before signing {deal}."
    reply = ep["finance"].build("research", "deal-review", verdict, vault=vault, chat_id=chat)
    say(wire(reply))
    log["verdict"] = ep["research"].open(reply)["body"]

    say("\n3 · research → mailer: a single-use capability to email the contact, no address")
    token = caps.issue("mailer", "send_email", chat, person)
    handoff = ep["research"].build("mailer", "deal-review", f"Email {person} the finance verdict.", vault=vault, chat_id=chat, caps=[token])
    say(wire(handoff))
    received = ep["mailer"].open(handoff)

    say("\n4 · mailer redeems it through the executor; the user sees the real preview and confirms")
    action = executor.propose_with_capability(caps, received["caps"][0], "mailer", "send_email",
                                              {"to": [person], "subject": f"Finance view on {deal}", "body": f"Hi {person}, {log['verdict']}"})
    say(json.dumps({"status": action.status, "preview_to": action.preview.get("to"), "preview_body": action.preview.get("body")},
                   ensure_ascii=False, indent=2))
    done = executor.confirm(action.action_id)
    say(f"agent sees: {json.dumps(done.for_agent(), ensure_ascii=False)}")
    log["outbox"] = vault.outbox(chat)[0]["payload"]

    say("\n5 · attacks")
    attempts = {}
    tampered = {**ask, "body": ask["body"].replace("fair", "unfair")}
    for name, fn in [
        ("tampered envelope", lambda: ep["finance"].open(tampered)),
        ("replayed envelope", lambda: ep["finance"].open(ask)),
        ("eve re-addresses the envelope to herself", lambda: ep["eve"].open({**ask, "to": "eve"})),
        ("eve decrypts the sealed amount with her own key", lambda: unseal(
            ask["sealed"][0], eve.box_key, canonical({**{k: ask[k] for k in ("v", "from", "to", "conv", "nonce", "ts")}, "label": price}))),
        ("capability reused", lambda: executor.propose_with_capability(caps, token, "mailer", "send_email", {"to": [person], "subject": "x", "body": "x"})),
        ("capability for another person", lambda: executor.propose_with_capability(
            caps, caps.issue("mailer", "send_email", chat, person), "mailer", "send_email",
            {"to": ["<PERSON_9>"], "subject": "x", "body": "x"})),
        ("finance seals a value back (policy is one-way)", lambda: ep["finance"].build("research", "x", "x", vault=vault, chat_id=chat, seal_labels=[price])),
    ]:
        try:
            fn()
            attempts[name] = "ALLOWED"
        except ProtocolError as exc:
            attempts[name] = f"rejected: {exc}"
        say(f"  {name}: {attempts[name]}")
    log["attacks"] = attempts

    log["audit"] = vault.verify_audit()
    say(f"\n6 · audit chain: {log['audit']}")
    return log


def main() -> int:
    log = run()
    ok = (not log["ask_on_wire_has_values"] and all(v.startswith("rejected") for v in log["attacks"].values())
          and log["audit"]["ok"] and log["outbox"]["to"] == ["priya@kestrel.io"])
    print("\nDEMO", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
