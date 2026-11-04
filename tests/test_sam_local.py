import base64
import io
import threading
from http.server import ThreadingHTTPServer

import httpx
from PIL import Image

from muse_shield.images import image_models_from_env
from muse_shield.images.meta import Box, Sam, parse_sam_boxes
from muse_shield.images.sam_local import format_boxes, make_handler, read_request


def png(w=120, h=80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


def test_output_matches_the_cloud_format_and_parses_back():
    text = format_boxes([(10.4, 5, 50.6, 40), (-3, 0, 2000, 70), (5, 5, 5, 9)], [0.91, 0.5, 0.9], 120, 80)
    assert text == "<0f>0<|box;x1=10;y1=5;x2=51;y2=40;w=120;h=80;c=0.910|>,1<|box;x1=0;y1=0;x2=120;y2=70;w=120;h=80;c=0.500|>"
    assert parse_sam_boxes(text) == [Box(10, 5, 51, 40), Box(0, 0, 120, 70)]  # clamped; empty box dropped


def test_request_reader_refuses_remote_urls():
    body = {"input": [{"content": [{"type": "input_image", "image_url": "https://example.com/x.png"},
                                   {"type": "input_text", "text": "face"}]}]}
    try:
        read_request(body)
        raise AssertionError("should refuse")
    except ValueError as exc:
        assert "data: URLs" in str(exc)


class FakeSegmenter:
    def __init__(self):
        self.seen = []

    def boxes(self, image: bytes, concept: str):
        self.seen.append((len(image), concept))
        return format_boxes([(20, 10, 60, 50)] if concept == "face" else [], [0.88], 120, 80), 12.0


def test_engine_sam_client_talks_to_the_local_server(monkeypatch):
    seg = FakeSegmenter()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(seg, "sam3-local (test)"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        assert httpx.get(url + "/health").json()["ok"]
        sam = Sam(url, "local", model="sam3-local")
        boxes, _ = sam.boxes(png(), "image/png", "face")
        assert boxes == [Box(20, 10, 60, 50)] and seg.seen == [(len(png()), "face")]
        assert sam.boxes(png(), "image/png", "license plate")[0] == []
        bad = httpx.post(url + "/responses", json={"input": []})
        assert bad.status_code == 400

        monkeypatch.setenv("MUSE_SHIELD_DEV_RAW_ANALYSIS", "1")
        monkeypatch.setenv("MODEL_API_KEY", "k")
        monkeypatch.setenv("MUSE_SHIELD_SAM_URL", url)
        vision, sam, why = image_models_from_env()
        assert not why and sam.base_url == url and sam.model == "sam3-local" and vision.model == "muse-spark-1.3"
    finally:
        server.shutdown()


def test_cloud_sam_by_default(monkeypatch):
    monkeypatch.setenv("MUSE_SHIELD_DEV_RAW_ANALYSIS", "1")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    _, sam, _ = image_models_from_env()
    assert sam.base_url == "https://api.meta.ai/v1" and sam.model == "sam-3.1"
