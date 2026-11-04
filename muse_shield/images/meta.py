"""Meta Model API clients for images: Muse Spark finds what's sensitive, SAM 3.1 finds faces precisely.

Both see the raw image, so like call 1 for text they're for made-up data until a self-hosted
model takes over. Coordinates come back in two systems:
    Muse Spark   bbox {x_min, y_min, x_max, y_max} on a 0-1000 grid of the image
    SAM 3.1      <|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|> in source pixels
and both are converted to pixel Boxes here.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field

import httpx

from ..analysis import ENTITY_TYPES
from ..backends import BackendError

FIND_PROMPT = """You protect people's privacy. Find everything in this image that could identify a person or leak a secret.

Return one JSON object and nothing else:
{"text": "every readable line of text in the image, in reading order, one per line",
 "items": [{"text": "the exact visible characters", "type": "TYPE", "bbox": {"x_min": 0, "y_min": 0, "x_max": 0, "y_max": 0}}],
 "visual": [{"kind": "KIND", "bbox": {"x_min": 0, "y_min": 0, "x_max": 0, "y_max": 0}}]}

items: sensitive text values. TYPE is one of PERSON, ORG, ADDRESS, LOCATION, CONTACT (phone, email, handle, UPI id),
ID (ID, account, card, case, invoice or tax number, IP), AMOUNT, DATE (birth dates, exact dates), SECRET (passwords,
PINs, CVVs, API keys, tokens), SENSITIVE_ATTRIBUTE (health, religion, ethnicity, sexuality, politics).
- One item per value: the name, not the whole line. Never list field labels such as "NAME", "DOB" or "Total".
- If a value appears twice (for example in a machine-readable line), list each occurrence with its own box.
- Public text is not personal: street and route signs, shop signs, logos and brand names on products or vehicles,
  slogans, headlines. Only list them when they identify a private person (a name tag, a house number with a street).
visual: faces (kind "face"), signatures ("signature"), QR codes ("qr_code"), barcodes ("barcode"),
license plates ("license_plate"), and photos on ID cards ("photo_id").
Boxes are on the 0-1000 grid of this image, tight around the text or object. Use [] when there is nothing."""

VISUAL_KINDS = {"face", "signature", "qr_code", "barcode", "license_plate", "photo_id"}
_SAM_BOX = re.compile(r"<\|box;x1=(-?\d+);y1=(-?\d+);x2=(-?\d+);y2=(-?\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>")


@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def area(self) -> int:
        return max(0, self.x2 - self.x1) * max(0, self.y2 - self.y1)

    def overlap(self, other: "Box") -> float:
        """Intersection over the smaller box: 1.0 when one box sits inside the other."""
        w = min(self.x2, other.x2) - max(self.x1, other.x1)
        h = min(self.y2, other.y2) - max(self.y1, other.y1)
        if w <= 0 or h <= 0:
            return 0.0
        return w * h / max(1, min(self.area, other.area))

    def pad(self, px: int, width: int, height: int, py: int | None = None) -> "Box":
        py = px if py is None else py
        return Box(max(0, self.x1 - px), max(0, self.y1 - py), min(width, self.x2 + px), min(height, self.y2 + py))

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]


def grid_box(bbox: dict, width: int, height: int) -> Box | None:
    """A Muse Spark 0-1000 bbox as pixels, clamped (the model can step slightly outside the grid)."""
    try:
        x1, y1, x2, y2 = (float(bbox[k]) for k in ("x_min", "y_min", "x_max", "y_max"))
    except (KeyError, TypeError, ValueError):
        return None
    clamp = lambda v: min(1000.0, max(0.0, v))  # noqa: E731
    x1, x2 = sorted((clamp(x1), clamp(x2)))
    y1, y2 = sorted((clamp(y1), clamp(y2)))
    box = Box(round(x1 / 1000 * width), round(y1 / 1000 * height), round(x2 / 1000 * width), round(y2 / 1000 * height))
    return box if box.area > 0 else None


@dataclass
class Finding:
    text: str = ""
    items: list[dict] = field(default_factory=list)   # {text, type, box}
    visual: list[dict] = field(default_factory=list)  # {kind, box}
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0


def data_url(image: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(image).decode()}"


def _post(client: httpx.Client, url: str, api_key: str, payload: dict, timeout: float, name: str) -> dict:
    for attempt in range(6):
        try:
            r = client.post(url, json=payload, timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})
        except httpx.HTTPError as exc:
            raise BackendError(f"{name}: {exc}") from exc
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 5:
            time.sleep(float(r.headers.get("retry-after") or min(2 ** attempt, 20)))
            continue
        if r.status_code >= 400:
            raise BackendError(f"{name}: HTTP {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError as exc:
            raise BackendError(f"{name}: response is not JSON") from exc
    raise BackendError(f"{name}: gave up after retries")


class SparkVision:
    """Muse Spark reads the image: its text, the sensitive values in it, and faces or codes, with boxes."""

    def __init__(self, base_url: str, model: str, api_key: str, *, client: httpx.Client | None = None,
                 reasoning_effort: str = "minimal", max_tokens: int = 8192, timeout: float = 180.0):
        if not api_key:
            raise BackendError("muse_spark vision: missing API key")
        if "contributor" in model:
            raise BackendError(f"{model} lets Meta train on prompts; images only go to Standard models")
        self.base_url, self.model, self.api_key = base_url.rstrip("/"), model, api_key
        self.reasoning_effort, self.max_tokens, self.timeout = reasoning_effort, max_tokens, timeout
        self._client = client or httpx.Client()

    def find(self, image: bytes, mime: str, width: int, height: int) -> Finding:
        payload = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                   "reasoning_effort": self.reasoning_effort, "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": [
                       {"type": "image_url", "image_url": {"url": data_url(image, mime)}},
                       {"type": "text", "text": FIND_PROMPT}]}]}
        t0 = time.perf_counter()
        data = _post(self._client, f"{self.base_url}/chat/completions", self.api_key, payload, self.timeout, "muse_spark vision")
        latency = (time.perf_counter() - t0) * 1000
        try:
            raw = data["choices"][0]["message"]["content"] or ""
            obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise BackendError(f"muse_spark vision: not the JSON contract ({exc})") from exc
        usage = data.get("usage") or {}
        out = Finding(text=str(obj.get("text") or ""), latency_ms=latency,
                      usage={"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                             "cached_in": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)})
        for it in obj.get("items") or []:
            box = grid_box(it.get("bbox") or {}, width, height) if isinstance(it, dict) else None
            text, etype = str(it.get("text") or "").strip() if box else "", str(it.get("type") or "").upper()
            if box and text:
                out.items.append({"text": text, "type": etype if etype in ENTITY_TYPES else "ID", "box": box})
        for v in obj.get("visual") or []:
            box = grid_box(v.get("bbox") or {}, width, height) if isinstance(v, dict) else None
            kind = str(v.get("kind") or "").lower()
            if box and kind in VISUAL_KINDS:
                out.visual.append({"kind": kind, "box": box})
        return out


    def locate(self, crop: bytes, mime: str, width: int, height: int, value: str) -> tuple[Box | None, dict]:
        """Where exactly `value` is inside a crop (pixels of the crop), or None if Spark can't see it.
        Grounding on a small crop is much tighter than on the whole image."""
        prompt = (f'Find the text "{value}" in this image. Return one JSON object: '
                  '{"found": true, "bbox": {"x_min": 0, "y_min": 0, "x_max": 0, "y_max": 0}} with the box on the 0-1000 '
                  'grid of this image, tight around exactly those characters, or {"found": false} if it is not visible.')
        payload = {"model": self.model, "temperature": 0, "max_tokens": 2048, "reasoning_effort": self.reasoning_effort,
                   "response_format": {"type": "json_object"},
                   "messages": [{"role": "user", "content": [
                       {"type": "image_url", "image_url": {"url": data_url(crop, mime)}}, {"type": "text", "text": prompt}]}]}
        data = _post(self._client, f"{self.base_url}/chat/completions", self.api_key, payload, self.timeout, "muse_spark locate")
        usage = data.get("usage") or {}
        used = {"in": usage.get("prompt_tokens", 0), "out": usage.get("completion_tokens", 0),
                "cached_in": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)}
        try:
            raw = data["choices"][0]["message"]["content"] or ""
            obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except (KeyError, IndexError, TypeError, ValueError):
            return None, used
        if not obj.get("found"):
            return None, used
        return grid_box(obj.get("bbox") or {}, width, height), used


class Sam:
    """SAM 3.1 over the Responses API: every match of one short concept ("face"), as pixel boxes."""

    def __init__(self, base_url: str, api_key: str, *, model: str = "sam-3.1", client: httpx.Client | None = None,
                 timeout: float = 120.0):
        if not api_key:
            raise BackendError("sam: missing API key")
        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout
        self._client = client or httpx.Client()

    def boxes(self, image: bytes, mime: str, concept: str) -> tuple[list[Box], float]:
        payload = {"model": self.model, "input": [{"role": "user", "content": [
            {"type": "input_image", "image_url": data_url(image, mime)},
            {"type": "input_text", "text": concept}]}]}
        t0 = time.perf_counter()
        data = _post(self._client, f"{self.base_url}/responses", self.api_key, payload, self.timeout, "sam")
        text = data.get("output_text") or "".join(
            c.get("text", "") for o in data.get("output") or [] for c in (o.get("content") or []) if isinstance(c, dict))
        return parse_sam_boxes(text), (time.perf_counter() - t0) * 1000


def parse_sam_boxes(text: str) -> list[Box]:
    """Boxes from SAM's special-token output (masks are ignored: boxes are what we blur)."""
    out = []
    for m in _SAM_BOX.finditer(text):
        x1, y1, x2, y2 = (int(v) for v in m.groups()[:4])
        if x2 > x1 and y2 > y1:
            out.append(Box(x1, y1, x2, y2))
    return out
