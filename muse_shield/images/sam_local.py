"""SAM 3 on this Mac, behind the same API the engine uses for cloud SAM 3.1.

Runs in the ML venv on the SSD (torch + ultralytics), never in the project .venv:

    source /Volumes/MajjiR/ai/env.sh
    python muse_shield/images/sam_local.py --weights /Volumes/MajjiR/ai/models/sam3.pt --port 8790

then point the engine at it:

    MUSE_SHIELD_SAM_URL=http://127.0.0.1:8790/v1

It answers POST /v1/responses with the cloud's request shape (an input_image data URL and an
input_text concept) and its special-token output (<0f>0<|box;x1=..;...;w=..;h=..;c=..|>, ...), so
muse_shield.images.meta.Sam talks to either one. Masks aren't returned: the engine blurs boxes.
The image never leaves this machine. Standalone on purpose: no muse_shield imports.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def format_boxes(boxes: list[tuple[float, float, float, float]], confs: list[float], width: int, height: int) -> str:
    """SAM 3.1's output format, one frame: <0f>0<|box;...|>,1<|box;...|>"""
    records = []
    for i, ((x1, y1, x2, y2), c) in enumerate(zip(boxes, confs)):
        x1, y1 = max(0, round(x1)), max(0, round(y1))
        x2, y2 = min(width, round(x2)), min(height, round(y2))
        if x2 > x1 and y2 > y1:
            records.append(f"{i}<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={width};h={height};c={c:.3f}|>")
    return "<0f>" + ",".join(records)


def read_request(body: dict) -> tuple[bytes, str]:
    """(image bytes, concept) from a Responses API body."""
    parts = body["input"][0]["content"]
    url = next(p["image_url"] for p in parts if p.get("type") == "input_image")
    text = next(p["text"] for p in parts if p.get("type") == "input_text").strip()
    if not url.startswith("data:"):
        raise ValueError("local SAM only takes data: URLs (it never fetches the network)")
    return base64.b64decode(url.split(",", 1)[1]), text


class Segmenter:
    """One SAM 3 model, loaded once; requests are served one at a time (one GPU)."""

    def __init__(self, weights: str, device: str, conf: float, half: bool, imgsz: int = 1008):
        import os

        os.environ["YOLO_AUTOINSTALL"] = "false"  # ultralytics must never pip-install anything at runtime
        from ultralytics.models.sam import SAM3SemanticPredictor  # heavy: only in the ML venv

        # save=False: the server must never write the pictures it sees (or their masks) to disk.
        overrides = dict(model=weights, task="segment", mode="predict", conf=conf, device=device, imgsz=imgsz,
                         save=False, verbose=False)
        if half:
            overrides["half"] = True
        self.predictor = SAM3SemanticPredictor(overrides=overrides)
        self.lock = threading.Lock()
        # The network is built on the first image, so do that now: the server is ready when it says so.
        buf = io.BytesIO()
        __import__("PIL.Image", fromlist=["Image"]).new("RGB", (64, 64), (128, 128, 128)).save(buf, "PNG")
        self.boxes(buf.getvalue(), "face")

    def boxes(self, image: bytes, concept: str) -> tuple[str, float]:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(image)).convert("RGB")
        w, h = img.size
        t0 = time.perf_counter()
        with self.lock:
            self.predictor.set_image(np.ascontiguousarray(np.asarray(img)[:, :, ::-1]))  # ultralytics expects BGR arrays
            result = self.predictor(text=[concept])[0]
        b = result.boxes
        boxes = b.xyxy.tolist() if b is not None and len(b) else []
        confs = b.conf.tolist() if b is not None and len(b) else []
        return format_boxes(boxes, confs, w, h), (time.perf_counter() - t0) * 1000


def make_handler(seg: Segmenter, model_name: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") in ("/health", "/v1/health"):
                return self._send(200, {"ok": True, "model": model_name})
            self._send(404, {"error": {"message": "not found"}})

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/v1/responses":
                return self._send(404, {"error": {"message": "not found"}})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                image, concept = read_request(body)
                text, ms = seg.boxes(image, concept)
            except (KeyError, IndexError, TypeError, StopIteration, ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": {"message": f"bad request: {exc}"}})
            self._send(200, {"model": model_name, "output": [{"content": [{"type": "output_text", "text": text}]}],
                             "usage": {"images_processed": 1, "latency_ms": round(ms, 1)}})

        def log_message(self, fmt, *args):  # one line per request, no request bodies
            print(f"{self.address_string()} {fmt % args}", flush=True)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(prog="sam_local")
    ap.add_argument("--weights", required=True, help="path to sam3.pt")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--half", action="store_true", help="fp16 (faster on MPS, check accuracy first)")
    ap.add_argument("--imgsz", type=int, default=1008, help="input size; 1008 is SAM 3's native, 644 is faster")
    args = ap.parse_args()
    t0 = time.time()
    seg = Segmenter(args.weights, args.device, args.conf, args.half, args.imgsz)
    name = f"sam3-local ({args.device}, {args.imgsz}px{', fp16' if args.half else ''})"
    print(f"loaded {args.weights} on {args.device} in {time.time() - t0:.1f}s; listening on 127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(seg, name)).serve_forever()


if __name__ == "__main__":
    main()
