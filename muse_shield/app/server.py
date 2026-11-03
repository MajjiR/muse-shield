"""FastAPI app on 127.0.0.1 (localhost only: it can decrypt the vault)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .. import __version__

WEB = Path(__file__).resolve().parents[2] / "web"


def create_app() -> FastAPI:
    app = FastAPI(title="Muse Shield", version=__version__, docs_url="/docs")

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/")
    def index():
        page = WEB / "index.html"
        return FileResponse(page) if page.exists() else {"ok": True, "hint": "web UI not built yet"}

    return app
