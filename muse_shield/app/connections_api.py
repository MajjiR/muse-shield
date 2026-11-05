"""Connections: sign in to Gmail/Calendar/Contacts (Google) and Telegram from the app, and pick a documents folder.

Sign-ins are kept encrypted in the vault. Until a service is connected its tools use the bundled sample
data, so the app works (and demos) either way. Disconnecting deletes the sign-in here and asks the service
to end it too.
"""

from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..connectors import folder, google, telegram
from .vault import Vault

FOLDER = "documents_folder"


class TelegramStart(BaseModel):
    phone: str


class TelegramVerify(BaseModel):
    code: str = ""
    password: str = ""


class FolderChoice(BaseModel):
    path: str


def _page(title: str, text: str) -> HTMLResponse:
    """The tab Google sends you back to: say what happened and close itself."""
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<body style="font:15px system-ui;margin:12vh auto;max-width:28rem;text-align:center;color:#222">
<h2 style="font-weight:600">{html.escape(title)}</h2><p>{html.escape(text)}</p>
<script>setTimeout(() => window.close(), 1500)</script></body>""")


def apply_folder(vault: Vault) -> None:
    """Point the documents connector at the folder you chose (kept in the vault across restarts)."""
    chosen = vault.secret(FOLDER)
    if chosen and Path(chosen["path"]).is_dir():
        os.environ["MUSE_SHIELD_FILES"] = chosen["path"]


def folder_files(path: str, limit: int = 2000) -> dict:
    """What Muse Spark can open in a folder: how many supported files, and the first few names (for the card)."""
    names, count = [], 0
    for i, p in enumerate(sorted(Path(path).rglob("*"))):
        if i >= limit:
            break
        if any(part.startswith(".") for part in p.relative_to(path).parts) or p.is_dir() or not folder._kind(p):
            continue
        count += 1
        if len(names) < 6:
            names.append(str(p.relative_to(path)))
    return {"count": count, "names": names}


def add_connection_routes(app: FastAPI, vault: Vault) -> None:
    apply_folder(vault)

    @app.get("/connections")
    def connections():
        chosen = vault.secret(FOLDER)
        return {"google": google.status(vault), "telegram": telegram.status(vault),
                "folder": {"configured": True, "connected": bool(chosen), "path": (chosen or {}).get("path"),
                           "sample": str(folder.root()) if not chosen else None,
                           "files": folder_files(chosen["path"]) if chosen and Path(chosen["path"]).is_dir() else None,
                           "can_browse": sys.platform == "darwin"}}

    # -- Google ----------------------------------------------------------------------------
    @app.post("/connections/google/start")
    def google_start(request: Request):
        try:
            return {"url": google.start(str(request.base_url).rstrip("/") + "/connections/google/callback")}
        except google.GoogleError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/connections/google/callback")
    def google_callback(code: str = "", state: str = "", error: str = ""):
        if error:
            return _page("Not connected", "Google sign-in was cancelled. You can close this tab.")
        try:
            google.finish(vault, code, state)
        except (google.GoogleError, KeyError) as exc:
            return _page("Not connected", str(exc))
        return _page("Google connected", "Muse Shield can now read and send for you, always masked and with your OK. "
                                          "You can close this tab.")

    @app.delete("/connections/google")
    def google_disconnect():
        google.disconnect(vault)
        return google.status(vault)

    # -- Telegram --------------------------------------------------------------------------
    @app.post("/connections/telegram/start")
    def telegram_start(body: TelegramStart):
        try:
            return telegram.start(vault, body.phone.strip())
        except Exception as exc:  # Telethon raises many error types; show the reason, never the session
            raise HTTPException(400, f"Telegram: {exc}") from exc

    @app.post("/connections/telegram/verify")
    def telegram_verify(body: TelegramVerify):
        try:
            return telegram.verify(vault, body.code.strip(), body.password)
        except Exception as exc:
            raise HTTPException(400, f"Telegram: {exc}") from exc

    @app.delete("/connections/telegram")
    def telegram_disconnect():
        telegram.disconnect(vault)
        return telegram.status(vault)

    # -- documents folder ------------------------------------------------------------------
    @app.post("/connections/folder")
    def choose_folder(body: FolderChoice):
        path = Path(body.path).expanduser()
        if not path.is_dir():
            raise HTTPException(400, f"no folder at {body.path}")
        vault.save_secret(FOLDER, {"path": str(path.resolve())})  # a path can say a lot about you; kept encrypted too
        apply_folder(vault)
        return {"connected": True, "path": str(path.resolve())}

    @app.post("/connections/folder/pick")
    def pick_folder():
        """Open the Mac's own folder picker on this computer (the engine runs here, so it can) and use the choice."""
        if sys.platform != "darwin":
            raise HTTPException(400, "the folder picker is Mac only; type the folder's path instead")
        r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Pick a folder for Muse Shield to read")'],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not r.stdout.strip():
            raise HTTPException(400, "no folder chosen")
        return choose_folder(FolderChoice(path=r.stdout.strip()))

    @app.delete("/connections/folder")
    def forget_folder():
        vault.delete_secret(FOLDER)
        os.environ.pop("MUSE_SHIELD_FILES", None)
        return {"connected": False}
