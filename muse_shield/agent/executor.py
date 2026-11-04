"""The only code allowed to turn placeholders into real values, and only to run a tool.

propose()  check the call against the tool's rules; side-effect tools become a pending
           action with a preview of the real values for the user, others run at once
confirm()  run a pending action
deny()     drop it
Every action is kept, encrypted, in the vault, so a pending confirmation and the history
of what ran survive an engine restart.
Whatever a tool returns is masked again (real vault values -> their placeholders) before
it goes back to any agent. A tool that reads private data (an inbox) brings back values the
vault has never seen, so its result also goes through the masker first; if that can't run,
the result is dropped and the action fails, rather than reaching a model unmasked.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from ..app.vault import Vault
from .policy import Checked, check
from .runners import RUNNERS
from .tools import TOOLS

SKIP_KEYS = {"id", "status", "date", "start", "end", "ts", "channel", "shared_outside", "outbox_id", "note_id",
             "message_id", "kind", "items", "columns", "rows", "count",
             "value", "result"}  # structure, not content; computed totals are already <RESULT_n> placeholders


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
    origin: str = "direct"  # "chat" when the chat model proposed it: deciding it continues that conversation
    mask_cost_usd: float = 0.0  # masking a private result (one analysis call per text field)

    def for_agent(self) -> dict:
        """What an agent may see: no real values."""
        return {"action_id": self.action_id, "tool": self.tool, "status": self.status, "violations": self.violations,
                "result": self.result, "error": self.error}

    def for_user(self) -> dict:
        return {**self.for_agent(), "chat_id": self.chat_id, "args": self.args, "preview": self.preview,
                "recipients": self.recipients, "unmasked": self.unmasked, "created_at": self.created_at,
                "mask_cost_usd": self.mask_cost_usd}


def remask(value, mapping: dict[str, str]):
    """Replace every real vault value in a tool result with its placeholder (longest values first)."""
    text = json.dumps(value, ensure_ascii=False)
    for label, real in sorted(mapping.items(), key=lambda kv: -len(kv[1])):
        if len(real) >= 3:
            text = text.replace(json.dumps(real, ensure_ascii=False)[1:-1], label)
    return json.loads(text)


class Executor:
    def __init__(self, vault: Vault, runners: dict | None = None, masker=None):
        self.vault, self.runners, self.masker = vault, runners or RUNNERS, masker
        self.actions: dict[str, Action] = {a["action_id"]: Action(**a) for a in vault.actions()}

    def _save(self, action: Action) -> Action:
        self.vault.save_action(action.action_id, action.chat_id, asdict(action), action.created_at)
        return action

    def propose(self, chat_id: str, tool: str, args: dict, origin: str = "direct") -> Action:
        checked: Checked = check(self.vault, chat_id, tool, args)
        action = Action("x_" + uuid.uuid4().hex[:10], chat_id, tool, dict(args), "pending", checked.violations,
                        checked.real, checked.recipients, checked.unmasked, origin=origin)
        self.actions[action.action_id] = action
        if not checked.ok:
            action.status, action.preview = "refused", {}
            self.vault.audit("tool_refused", chat_id, {"tool": 1})
            return self._save(action)
        self.vault.audit("tool_proposed", chat_id, {"tool": 1, "unmasked": len(checked.unmasked)})
        return self._run(action) if not checked.tool.side_effect else self._save(action)

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

    def _mask_result(self, action: Action, value):
        """Run every text field through the masker (values seen here first are marked as from a tool)."""
        if self.masker is None:
            raise RuntimeError(f"{action.tool} reads private data and masking is off, so its result wasn't used")
        leaves: list[tuple[list, object]] = []

        def walk(node, path):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k not in SKIP_KEYS:
                        walk(v, path + [k])
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, path + [i])
            elif isinstance(node, str) and len(node.strip()) >= 3:
                leaves.append((path, node))

        walk(value, [])
        origin = "user" if TOOLS[action.tool].trusted_source else "tool"  # your own address book counts as you
        mask = lambda text: self.masker.mask(text, action.chat_id, propagate=True, contexts=False, title=False, origin=origin)  # noqa: E731
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(mask, [text for _, text in leaves]))
        action.mask_cost_usd = round(sum(m.cost_usd or 0 for m in results), 6)
        if bad := next((m for m in results if not m.analysis_ok), None):
            raise RuntimeError(f"couldn't mask the {action.tool} result ({bad.error}), so it wasn't used")
        out = json.loads(json.dumps(value))
        for (path, _), m in zip(leaves, results):
            node = out
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = m.masked_text
        return out

    def deny(self, action_id: str) -> Action:
        action = self._pending(action_id)
        action.status, action.preview = "denied", {}
        self.vault.consent(action.chat_id, action.tool, "execute", "deny", "")
        return self._save(action)

    def _pending(self, action_id: str) -> Action:
        action = self.actions.get(action_id)
        if action is None or action.status != "pending":
            raise KeyError("unknown or already handled action")
        return action

    def _run(self, action: Action) -> Action:
        try:
            real = self.runners[action.tool](self.vault, action.chat_id, action.preview)
            if TOOLS[action.tool].reads_private:
                real = self._mask_result(action, real)
            action.result, action.status = remask(real, self.vault.mapping(action.chat_id)), "done"
            self.vault.audit("tool_run", action.chat_id, {"tool": 1})
        except Exception as exc:  # a failing tool must not leak values through its error text
            action.status, action.error = "failed", remask(str(exc), self.vault.mapping(action.chat_id))
            self.vault.audit("tool_failed", action.chat_id, {"tool": 1})
        action.preview = {} if action.status != "pending" else action.preview
        return self._save(action)
