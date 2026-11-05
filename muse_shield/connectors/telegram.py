"""Telegram, signed in as you: read your chats and send a message to one of them.

The app ships one Telegram API id (MUSE_SHIELD_TELEGRAM_API_ID / _API_HASH, from my.telegram.org); each
person signs in with their phone number, the code Telegram sends, and their two-step password if set.
The session is kept encrypted in the vault. Chats are addressed by opaque ids from the last listing, so a
model can only send to a chat you already have, never to a username an incoming message suggests.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable

from ..app.vault import Vault
from . import opaque_id

SECRET, PENDING, CHATS = "telegram", "telegram_pending", "telegram_chats"
MAX_CHATS, MAX_MESSAGES = 15, 20


class TelegramError(RuntimeError):
    pass


def api() -> tuple[int, str] | None:
    try:
        return int(os.environ["MUSE_SHIELD_TELEGRAM_API_ID"]), os.environ["MUSE_SHIELD_TELEGRAM_API_HASH"]
    except (KeyError, ValueError):
        return None


def _client(session: str = ""):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    cfg = api()
    if not cfg:
        raise TelegramError("Telegram sign-in isn't set up in this build (no API id)")
    return TelegramClient(StringSession(session), cfg[0], cfg[1])


make_client: Callable = _client  # tests swap in a fake


def _run(coro_fn):
    """Telethon is asyncio; each call gets its own loop and connection (the engine's routes are sync)."""
    return asyncio.run(coro_fn())


def status(vault: Vault) -> dict:
    saved = vault.secret(SECRET)
    return {"configured": api() is not None, "connected": bool(saved), "account": (saved or {}).get("account"),
            "step": "code" if vault.secret(PENDING) else None, "services": ["Chats", "Messages"]}


def connected(vault: Vault) -> bool:
    return vault.secret(SECRET) is not None


# -- sign-in ---------------------------------------------------------------------------------
def start(vault: Vault, phone: str) -> dict:
    async def go():
        c = make_client()
        await c.connect()
        try:
            sent = await c.send_code_request(phone)
            return c.session.save(), sent.phone_code_hash
        finally:
            await c.disconnect()

    session, code_hash = _run(go)
    vault.save_secret(PENDING, {"phone": phone, "session": session, "hash": code_hash})
    return status(vault)


def verify(vault: Vault, code: str = "", password: str = "") -> dict:
    """Finish signing in. Returns {'step': 'password'} when the account has a two-step password."""
    from telethon.errors import SessionPasswordNeededError

    pending = vault.secret(PENDING)
    if not pending:
        raise TelegramError("start again: no sign-in in progress")

    async def go():
        c = make_client(pending["session"])
        await c.connect()
        try:
            try:
                if password and pending.get("needs_password"):
                    await c.sign_in(password=password)
                else:
                    await c.sign_in(pending["phone"], code, phone_code_hash=pending["hash"])
            except SessionPasswordNeededError:
                if not password:
                    return c.session.save(), None
                await c.sign_in(password=password)
            me = await c.get_me()
            name = " ".join(p for p in (me.first_name, me.last_name) if p) or me.username or "Telegram account"
            return c.session.save(), name
        finally:
            await c.disconnect()

    session, account = _run(go)
    if account is None:
        vault.save_secret(PENDING, {**pending, "session": session, "needs_password": True})
        return {**status(vault), "step": "password"}
    vault.save_secret(SECRET, {"session": session, "account": account})
    vault.delete_secret(PENDING)
    vault.audit("connect", None, {"telegram": 1})
    return status(vault)


def disconnect(vault: Vault) -> None:
    saved = vault.secret(SECRET)
    if saved:
        async def go():
            c = make_client(saved["session"])
            await c.connect()
            try:
                await c.log_out()  # ends the session on Telegram's side too
            finally:
                await c.disconnect()
        try:
            _run(go)
        except Exception:
            pass  # forget it here regardless
    for name in (SECRET, PENDING, CHATS):
        vault.delete_secret(name)
    vault.audit("disconnect", None, {"telegram": 1})


# -- read and send ---------------------------------------------------------------------------
def _session(vault: Vault) -> str:
    saved = vault.secret(SECRET)
    if not saved:
        raise TelegramError("Telegram isn't connected")
    return saved["session"]


def _kind(dialog) -> str:
    return "group" if dialog.is_group else "channel" if dialog.is_channel else "private"


def read_telegram(vault: Vault, chat_id: str, args: dict) -> dict:
    session = _session(vault)
    wanted = args.get("chat_id")
    known = vault.secret(CHATS) or {}

    async def go():
        c = make_client(session)
        await c.connect()
        try:
            dialogs = await c.get_dialogs(limit=MAX_CHATS)
            chats = {opaque_id("tg", str(d.id)): {"tg_id": d.id, "title": d.name or "", "kind": _kind(d)} for d in dialogs}
            if not wanted:
                rows = [{"id": opaque_id("tg", str(d.id)), "chat": d.name or "", "kind": _kind(d), "unread": str(d.unread_count),
                         "last": (d.message.message or "")[:200] if d.message else ""} for d in dialogs]
                return chats, {"status": f"{len(rows)} recent chats", "chats": rows}
            target = chats.get(wanted) or known.get(wanted)
            if not target:
                raise TelegramError(f"no chat with id {wanted}; list your chats first")
            msgs = await c.get_messages(target["tg_id"], limit=MAX_MESSAGES)
            rows = []
            for m in reversed(msgs):
                if not m.message:
                    continue
                sender = await m.get_sender()
                who = "You" if m.out else (" ".join(p for p in (getattr(sender, "first_name", None), getattr(sender, "last_name", None)) if p)
                                           or getattr(sender, "title", None) or "someone")
                rows.append({"id": str(m.id), "ts": m.date.isoformat() if m.date else "", "message": f"{who}: {m.message}"})
            return chats, {"status": f"{len(rows)} messages", "chat": target["title"], "kind": target["kind"], "messages": rows}
        finally:
            await c.disconnect()

    chats, result = _run(go)
    vault.save_secret(CHATS, {**known, **chats})  # so a send can only target a chat you have
    return result


def chat_info(vault: Vault, chat_id: str) -> dict | None:
    return (vault.secret(CHATS) or {}).get(chat_id)


def send_telegram(vault: Vault, chat_id: str, args: dict) -> dict:
    target = chat_info(vault, args["chat_id"])
    if not target:
        raise TelegramError("that isn't one of your chats")
    session = _session(vault)

    async def go():
        c = make_client(session)
        await c.connect()
        try:
            await c.get_dialogs(limit=MAX_CHATS)  # loads the chat's access hash into this session
            sent = await c.send_message(target["tg_id"], args["text"])
            return sent.id
        finally:
            await c.disconnect()

    message_id = _run(go)
    vault.add_outbox(chat_id, "send_telegram", {"chat": target["title"], "kind": target["kind"], "text": args["text"]})
    return {"status": f"sent on Telegram to {target['title']}", "message_id": str(message_id)}
