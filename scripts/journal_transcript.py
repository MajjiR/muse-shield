"""Turn an exported Claude Code session (transcript.jsonl) into a readable Markdown conversation.

    python3 scripts/journal_transcript.py journal/conversations/<session>/raw/transcript.jsonl \
        journal/conversations/<session>/conversation.md

Keeps every user message and every assistant text reply in full, in order, and lists
tool steps by their one-line description. Tool outputs and internal events are left
in the raw export next to it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _tool_line(block: dict) -> str:
    inp = block.get("input") or {}
    what = inp.get("description") or inp.get("query") or inp.get("url") or inp.get("file_path") or inp.get("path") or ""
    return f"- `{block.get('name', 'tool')}` {what}".rstrip()


def convert(src: Path) -> str:
    out = ["# Conversation transcript", ""]
    seen: set[str] = set()
    said: set[str] = set()  # user text already written (messages sent mid-turn arrive twice)

    def user(text: str, ts: str) -> None:
        text = text.strip()
        if text and text not in said:
            said.add(text)
            out.extend([f"## You · {ts}", "", text, ""])

    for line in src.read_text().splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = (d.get("timestamp") or "")[:16].replace("T", " ")
        if d.get("type") == "queue-operation" and d.get("operation") == "enqueue" and isinstance(d.get("content"), str):
            user(d["content"], ts)
            continue
        if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
            continue
        uid = d.get("uuid")
        if uid in seen:
            continue
        seen.add(uid)
        content = (d.get("message") or {}).get("content")
        if d["type"] == "user":
            if isinstance(content, str):
                user(content, ts)
            elif isinstance(content, list):
                user("\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"), ts)
            continue
        if not isinstance(content, list):
            continue
        texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text", "").strip()]
        tools = [_tool_line(b) for b in content if b.get("type") == "tool_use"]
        if texts:
            out += [f"## Claude · {ts}", "", "\n\n".join(texts), ""]
        if tools:
            out += tools + [""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    md = convert(Path(argv[1]))
    Path(argv[2]).write_text(md)
    print(f"wrote {argv[2]} ({len(md):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
