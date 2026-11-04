"""Document routes: upload a PDF, .docx or .pptx into a chat, follow its analysis, download the masked copy.

Uploads are a raw application/octet-stream body (not multipart, which spills large files to /tmp in
plaintext), with the file name and chat in headers. The file is masked in a background job.
"""

from __future__ import annotations

import re
import threading
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .. import documents
from .engine import Masker
from .vault import Vault

MEDIA = {"pdf": "application/pdf",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


def counts_by_type(spans: list[dict]) -> dict[str, int]:
    c = Counter((s["type"] if s["kind"] == "entity" else f"CONTEXT_{s['type']}") for s in spans)
    return dict(c)


def safe_stem(filename: str, spans: list[dict]) -> str:
    """The download name: the original stem with any masked value in it replaced by its placeholder."""
    stem = filename.rsplit(".", 1)[0] or "document"
    for s in sorted((s for s in spans if s["kind"] == "entity"), key=lambda s: -len(s["text"])):
        words = [re.escape(w) for w in re.split(r"[\s_.\-]+", s["text"]) if w]
        if words:
            stem = re.sub(r"[\s_.\-]*".join(words), s["placeholder"].strip("<>"), stem, flags=re.I)
    return re.sub(r"[^\w\-. ]+", "_", stem)[:80] or "document"


class DocumentJobs:
    """Masks one document at a time (each uses the masker's workers), so the analysis rate limit holds."""

    def __init__(self, vault: Vault, masker: Masker, inspector=None, sync: bool = False):
        self.vault, self.masker, self.inspector, self.sync = vault, masker, inspector, sync
        self.progress: dict[str, dict] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="documents")
        self._lock = threading.Lock()

    def submit(self, doc_id: str, chat_id: str, data: bytes, filename: str) -> None:
        if self.sync:
            self.run(doc_id, chat_id, data, filename)
        else:
            self._pool.submit(self.run, doc_id, chat_id, data, filename)

    def run(self, doc_id: str, chat_id: str, data: bytes, filename: str) -> None:
        from ..documents.pipeline import mask_document
        from ..documents.verify import verify

        def on_progress(done: int, total: int) -> None:
            with self._lock:
                self.progress[doc_id] = {"done": done, "total": total}

        if self.inspector:
            self.inspector.for_chat(chat_id)
        self.vault.update_document(doc_id, status="analysing", record={"filename": filename})
        try:
            md = mask_document(data, self.masker, chat_id, on_progress=on_progress)
            self.vault.update_document(doc_id, status="verifying")
            report = verify(md, filename)
        except documents.DocumentError as exc:
            self.vault.update_document(doc_id, status="failed", record={"filename": filename, "error": str(exc), "error_code": exc.code})
            return
        except Exception as exc:  # noqa: BLE001 - a failed job must not take the engine down
            self.vault.update_document(doc_id, status="failed", record={"filename": filename, "error": f"internal error: {type(exc).__name__}"})
            return
        finally:
            with self._lock:
                self.progress.pop(doc_id, None)
        counts = counts_by_type(md.masked.spans)
        record = {"filename": filename, "safe_stem": safe_stem(filename, md.masked.spans), "text": md.doc_text.text,
                  "masked_text": md.masked.masked_text, "spans": md.masked.spans, "units": md.doc_text.units,
                  "page_status": md.page_status, "verify": report.to_dict(), "cost_usd": md.masked.cost_usd,
                  "seconds": round(md.seconds, 2)}
        self.vault.update_document(doc_id, status="ready" if report.ok else "blocked", pages=md.pages, counts=counts,
                                   warnings=md.warnings + report.warnings, record=record, masked=md.data if report.ok else None)
        self.vault.audit("document_mask", chat_id, {**counts, "verified": int(report.ok)})


def add_document_routes(app: FastAPI, vault: Vault, masker: Masker | None, off_reason: str, inspector=None,
                        sync: bool = False) -> DocumentJobs | None:
    jobs = DocumentJobs(vault, masker, inspector, sync) if masker else None
    app.state.document_jobs = jobs

    def need_doc(doc_id: str) -> dict:
        d = vault.document(doc_id)
        if not d:
            raise HTTPException(404, "unknown document")
        return d

    def shown(d: dict) -> dict:
        if jobs and d["doc_id"] in jobs.progress:
            d["progress"] = jobs.progress[d["doc_id"]]
        return d

    @app.post("/documents")
    async def upload(request: Request):
        if not documents.available():
            raise HTTPException(503, "document support isn't installed (pip install 'muse-shield[documents]')")
        if not jobs:
            raise HTTPException(503, off_reason or "analysis is off")
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > documents.MAX_BYTES:
                raise HTTPException(413, f"files up to {documents.MAX_BYTES // (1024 * 1024)} MB")
        data = bytes(data)
        try:
            fmt = documents.sniff(data)
        except documents.DocumentError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        filename = urllib.parse.unquote(request.headers.get("x-filename", ""))[:255] or f"document.{fmt}"
        chat_id = vault.ensure_chat(request.headers.get("x-chat-id") or None)
        doc_id, n = vault.add_document(chat_id, fmt, data)
        jobs.submit(doc_id, chat_id, data, filename)
        return shown(vault.document(doc_id)) | {"n": n}

    @app.get("/documents/{doc_id}")
    def get_document(doc_id: str, detail: bool = False):
        need_doc(doc_id)
        return shown(vault.document(doc_id, detail=detail))

    @app.get("/documents/{doc_id}/masked")
    def download(doc_id: str):
        d = need_doc(doc_id)
        data = vault.document_blob(doc_id, "masked")
        if data is None:
            raise HTTPException(409, "no verified masked copy" if d["status"] in ("ready", "blocked") else "not ready yet")
        name = f"{d['safe_stem'] or 'document'}.masked.{d['format']}"
        vault.audit("document_download", d["chat_id"], {"documents": 1})
        return Response(data, media_type=MEDIA[d["format"]],
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}"})

    @app.get("/chats/{chat_id}/documents")
    def chat_documents(chat_id: str):
        return [shown(d) for d in vault.documents(chat_id)]

    @app.post("/documents/{doc_id}/delete")
    def delete_document(doc_id: str):
        need_doc(doc_id)
        return {"ok": vault.delete_document(doc_id)}

    return jobs

