"""Image routes for chats: upload a picture, get it masked and stored, attach it to a turn.

POST /images takes the raw bytes (like /documents: no multipart, so nothing lands in /tmp) and runs the
ImageMasker (Muse Spark vision + SAM 3.1, then a re-scan). Only the masked PNG is stored, sealed in the
vault; the original is never kept. /images/mask (stateless, JSON) stays for other clients.
"""

from __future__ import annotations

import urllib.parse
from collections import Counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from ..backends import BackendError
from .vault import Vault

MAX_IMAGE_BYTES = 20_000_000


def region_counts(regions: list[dict]) -> dict[str, int]:
    """Text values by type (PERSON, ID…) and visual regions by kind (face, qr…)."""
    return dict(Counter(r["type"] if r["kind"] == "text" else r["kind"] for r in regions))


def add_image_routes(app: FastAPI, vault: Vault, image_masker, images_off: str) -> None:
    @app.post("/images")
    async def upload_image(request: Request):
        if not image_masker:
            raise HTTPException(503, images_off or "image masking is off")
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_IMAGE_BYTES:
                raise HTTPException(413, "images up to 20 MB")
        filename = urllib.parse.unquote(request.headers.get("x-filename", ""))[:255] or "image"
        chat_id = vault.ensure_chat(request.headers.get("x-chat-id") or None)
        try:
            masked = image_masker.mask(bytes(data), chat_id, verify=True)
        except ValueError as exc:
            raise HTTPException(415, str(exc)) from exc
        except BackendError as exc:
            raise HTTPException(502, str(exc)) from exc
        verified = bool(masked.verify and masked.verify.get("ok"))
        counts = region_counts(masked.regions)
        record = {"filename": filename, "width": masked.width, "height": masked.height, "regions": masked.regions,
                  "masked_text": masked.text, "verify": masked.verify, "cost": masked.cost, "timings_ms": masked.timings_ms}
        image_id, _ = vault.add_image(chat_id, masked.image, record, verified, counts)
        return vault.image(image_id)

    @app.get("/images/{image_id}")
    def get_image(image_id: str):
        info = vault.image(image_id)
        if not info:
            raise HTTPException(404, "unknown image")
        return info

    @app.get("/images/{image_id}/masked")
    def masked_png(image_id: str, download: bool = False):
        info = vault.image(image_id)
        if not info:
            raise HTTPException(404, "unknown image")
        headers = {"Cache-Control": "no-store"}
        if download:
            headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{urllib.parse.quote(f'image-{info['n']}.masked.png')}"
        return Response(vault.image_png(image_id), media_type="image/png", headers=headers)

    @app.get("/chats/{chat_id}/images")
    def chat_images(chat_id: str):
        return vault.images(chat_id)
