"""The only code allowed to turn placeholders into real values, and only to run a tool.

propose()  check the call against the tool's rules; side-effect tools become a pending
           action with a preview of the real values for the user, others run at once
confirm()  run a pending action
deny()     drop it
Whatever a tool returns is masked again (real vault values -> their placeholders) before
it goes back to any agent.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field

from ..app.vault import Vault
from .policy import Checked, check
from .runners import RUNNERS


@dataclass
class Action:
    action_id: str
    chat_id: str
    tool: str
    args: dict  # as the agent wrote them (placeholders)
    status: str  # refused | pending | done | denied | failed
    violations: list[str] = field(default_factory=list)
    preview: dict = field(default_factory=dict)  # real arguments, shown to the user only
    recipients: list[dict] = field(default_factory=list)
    unmasked: list[str] = field(default_factory=list)
    result: dict = field(default_factory=dict)  # masked, safe to return to an agent
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def for_agent(self) -> dict:
        """What an agent may see: no real values."""
        return {"action_id": self.action_id, "tool": self.tool, "status": self.status, "violations": self.violations,
                "result": self.result, "error": self.error}

    def for_user(self) -> dict:
        return {**self.for_agent(), "chat_id": self.chat_id, "args": self.args, "preview": self.preview,
                "recipients": self.recipients, "unmasked": self.unmasked, "created_at": self.created_at}


def remask(value, mapping: dict[str, str]):
    """Replace every real vault value in a tool result with its placeholder (longest values first)."""
    text = json.dumps(value, ensure_ascii=False)
    for label, real in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        if len(real) >= 3:
            text = text.replace(json.dumps(real, ensure_ascii=False)[1:-1], label)
    return json.loads(text)


class Executor:
    def __init__(self, vault: Vault, runners: dict | None = None):
        self.vault, self.runners = vault, runners or RUNNERS
        self.actions: dict[str, Action] = {}

    def propose(self, chat_id: str, tool: str, args: dict) -> Action:
        checked: Checked = check(self.vault, chat_id, tool, args)
        action = Action("x_" + uuid.uuid4().hex[:10], chat_id, tool, dict(args), "pending", checked.violations,
                        checked.real, checked.recipients, checked.unmasked)
        self.actions[action.action_id] = action
        if not checked.ok:
            action.status, action.preview = "refused", {}
            self.vault.audit("tool_refused", chat_id, {"tool": 1})
            return action
        self.vault.audit("tool_proposed", chat_id, {"tool": 1, "unmasked": len(checked.unmasked)})
        return self._run(action) if not checked.tool.side_effect else action

    def propose_with_capability(self, caps, token: str, agent: str, tool: str, args: dict) -> Action:
        """A remote agent uses a capability: it may only target the one placeholder it was granted, with that tool."""
        from .protocol import ProtocolError

        claims = caps.redeem(token, agent, tool)  # raises ProtocolError: bad signature, expired, reused, wrong agent/tool
        recipients = {lbl for v in (args.get("to"), args.get("attendees")) if v
                      for lbl in re.findall(r"<[A-Z][A-Z_]*_\d+>", json.dumps(v))}
        if recipients - {claims["label"]}:
            raise ProtocolError(f"capability covers {claims['label']} only, not {sorted(recipients - {claims['label']})}")
        return self.propose(claims["chat"], tool, args)

    def confirm(self, action_id: str) -> Action:
        action = self._pending(action_id)
        self.vault.consent(action.chat_id, action.tool, "execute", "allow", f"unmasks {', '.join(action.unmasked) or 'nothing'}")
        return self._run(action)

    def deny(self, action_id: str) -> Action:
        action = self._pending(action_id)
        action.status, action.preview = "denied", {}
        self.vault.consent(action.chat_id, action.tool, "execute", "deny", "")
        return action

    def _pending(self, action_id: str) -> Action:
        action = self.actions.get(action_id)
        if action is None or action.status != "pending":
            raise KeyError("unknown or already handled action")
        return action

    def _run(self, action: Action) -> Action:
        try:
            real = self.runners[action.tool](self.vault, action.chat_id, action.preview)
            action.result, action.status = remask(real, self.vault.mapping(action.chat_id)), "done"
            self.vault.audit("tool_run", action.chat_id, {"tool": 1})
        except Exception as exc:  # a failing tool must not leak values through its error text
            action.status, action.error = "failed", remask(str(exc), self.vault.mapping(action.chat_id))
            self.vault.audit("tool_failed", action.chat_id, {"tool": 1})
        action.preview = {} if action.status != "pending" else action.preview
        return action
