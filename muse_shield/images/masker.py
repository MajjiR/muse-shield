"""Mask an image: SAM 3.1 (and optionally Muse Spark) finds what's sensitive, the vault names it, Pillow covers it.

Default (no reader): SAM 3.1 alone looks for each concept in SAM_ONLY_CONCEPTS, faces get an oval blur and
everything else (number plates, cards, documents, signatures, codes) is pixelated under a labelled bar. Nothing
reads the raw image's text, so the picture never goes to a chat model before it's masked. SAM can't find loose
text, so with MUSE_SHIELD_IMAGE_TEXT_CHECK=1 our Glimmer checks the masked picture and refuses it if private
text still shows. With a reader (MUSE_SHIELD_IMAGE_READER=spark):

    faces           SAM 3.1 "face" boxes (precise), plus any face Muse Spark sees that SAM missed -> oval blur
    ID photos       Muse Spark "photo_id" -> oval blur
    plates, codes,  SAM "license plate" and Muse Spark visual kinds -> pixelate, then a labelled bar
    signatures
    text values     Muse Spark items -> a bar labelled with the value's vault placeholder (<PERSON_1>), the same
                    label the value gets in text chats
Then, optionally, the masked image goes back to Muse Spark for a re-scan: any masked value it can still
read, or any face outside a blurred region, fails verification.
"""

from __future__ import annotations

import io
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from PIL import Image

from ..app.engine import placeholder_base
from ..app.vault import Vault
from ..backends import BackendError
from ..costs import run_cost
from .meta import Box, Finding, Sam, SparkVision, data_url
from .render import blur_oval, cover, pixelate

MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}
SAM_CONCEPTS = ("face", "license plate")  # with a reader, which finds text values and other objects itself
# SAM 3.1 alone: one request per concept, in parallel. MUSE_SHIELD_SAM_CONCEPTS overrides (comma-separated).
SAM_ONLY_CONCEPTS = ("face", "license plate", "id card", "credit card", "document", "signature", "qr code", "barcode")
BLUR_KINDS = {"face", "photo_id"}


class ImageRefused(ValueError):
    """The image can't be masked safely (private text, and nothing here reads text), so it isn't sent."""


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


@dataclass
class ImageMasked:
    chat_id: str
    image: bytes                                     # PNG
    width: int
    height: int
    regions: list[dict] = field(default_factory=list)  # {kind, type, label, box, source}
    text: str = ""                                   # what Muse Spark read, values replaced by placeholders
    verify: dict | None = None
    timings_ms: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    sam_images: int = 0

    def to_dict(self, with_image: bool = True) -> dict:
        out = {"chat_id": self.chat_id, "width": self.width, "height": self.height, "regions": self.regions,
               "masked_text": self.text, "verify": self.verify, "timings_ms": self.timings_ms, "cost": self.cost,
               "sam_images": self.sam_images}
        if with_image:
            out["image"] = data_url(self.image, "image/png")
        return out


def load(image: bytes) -> tuple[Image.Image, bytes, str]:
    """(RGB image, bytes to send, mime). Formats the API doesn't take are re-encoded as PNG."""
    try:
        img = Image.open(io.BytesIO(image))
        fmt = img.format or ""
        img = img.convert("RGB")
    except Exception as exc:  # Pillow raises several types for undecodable input
        raise ValueError(f"not an image: {exc}") from exc
    if fmt in MIMES:
        return img, image, MIMES[fmt]
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return img, buf.getvalue(), "image/png"


def refine_window(box: Box, W: int, H: int) -> Box:
    """The crop to re-ask about: Spark's full-image boxes can be a line off, so look a few lines around."""
    w, h = box.x2 - box.x1, box.y2 - box.y1
    dx, dy = max(80, w // 2), max(48, 2 * h)
    return Box(max(0, box.x1 - dx), max(0, box.y1 - dy), min(W, box.x2 + dx), min(H, box.y2 + dy))


def refine(vision: SparkVision, img: Image.Image, items: list[dict], pool: ThreadPoolExecutor) -> dict:
    """Snap each item's box to its text by asking Muse Spark again on a crop around it. Items whose
    value Spark can't find in the crop keep their first box. Returns token usage."""
    W, H = img.size

    def one(it: dict) -> tuple[Box | None, dict]:
        win = refine_window(it["box"], W, H)
        crop = img.crop(win.as_list())
        scale = max(1.0, 384 / max(1, min(crop.size)))  # small crops are upscaled so the text is legible
        if scale > 1:
            crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        try:
            box, used = vision.locate(buf.getvalue(), "image/png", crop.width, crop.height, it["text"])
        except BackendError:
            return None, {}
        if not box:
            return None, used
        return Box(win.x1 + round(box.x1 / scale), win.y1 + round(box.y1 / scale),
                   win.x1 + round(box.x2 / scale), win.y1 + round(box.y2 / scale)), used

    usage: dict = {}
    for it, (box, used) in zip(items, pool.map(one, items)):
        if box and box.area > 0:
            it["first_box"], it["box"], it["refined"] = it["box"], box, True
        for k, v in used.items():
            usage[k] = usage.get(k, 0) + v
    return usage


class ImageMasker:
    def __init__(self, vault: Vault, vision: SparkVision | None, sam: Sam | None = None, concepts=None,
                 refine: bool = True, workers: int = 16, text_check=None):
        if vision is None and sam is None:
            raise ValueError("image masking needs SAM 3.1, a reader, or both")
        concepts = concepts or (SAM_CONCEPTS if vision else SAM_ONLY_CONCEPTS)
        self.vault, self.vision, self.sam, self.concepts, self.refine = vault, vision, sam, tuple(concepts), refine
        # SAM can't read: with no reader, text_check(image, mime) -> (private text?, what) refuses images with text
        self.text_check = text_check
        self._pool = ThreadPoolExecutor(max_workers=workers)

    def mask(self, image: bytes, chat_id: str | None = None, verify: bool = True) -> ImageMasked:
        img, payload, mime = load(image)
        W, H = img.size
        chat_id = self.vault.ensure_chat(chat_id)
        t0 = time.perf_counter()

        found = self._pool.submit(self.vision.find, payload, mime, W, H) if self.vision else None
        sam_jobs = {c: self._pool.submit(self.sam.boxes, payload, mime, c) for c in self.concepts} if self.sam else {}
        finding: Finding = found.result() if found else Finding()
        t_refine = time.perf_counter()
        refine_usage = refine(self.vision, img, finding.items, self._pool) if self.refine and self.vision else {}
        refine_ms = (time.perf_counter() - t_refine) * 1000
        sam_boxes: dict[str, list[Box]] = {}
        sam_ms: list[float] = []
        for concept, job in sam_jobs.items():
            try:
                boxes, ms = job.result()
            except BackendError:
                if not self.vision:  # SAM is the only finder: a failed concept must not pass as "nothing found"
                    raise
                boxes, ms = [], 0.0  # Muse Spark's own face boxes still cover this case
            sam_boxes[concept], sam_ms = boxes, sam_ms + [ms]

        regions = self._regions(finding, sam_boxes, chat_id, W, H)
        out = img.copy()
        for r in regions:  # blur and pixelate first, so labelled bars sit on top
            box = Box(*r["box"])
            if r["kind"] in BLUR_KINDS:
                blur_oval(out, box)
            elif r["kind"] != "text":
                pixelate(out, box)
                cover(out, box, r["label"], img)
        for r in regions:
            if r["kind"] == "text":
                cover(out, Box(*r["box"]), r["label"], img)

        text = finding.text
        for r in sorted((r for r in regions if r["kind"] == "text"), key=lambda r: -len(r["value"])):
            text = text.replace(r["value"], r["label"])
        buf = io.BytesIO()
        out.save(buf, "PNG")
        # SAM can't read, so with no reader our Glimmer looks at the MASKED picture: a number plate, card or document
        # SAM has covered is fine; private text still showing (a printed name, a chat) means it isn't sent.
        checked = self.text_check is not None and not self.vision
        if checked:
            try:
                has_text, what = self.text_check(buf.getvalue(), "image/png")
            except BackendError as exc:
                raise ImageRefused(f"couldn't check this image for private text, so it wasn't sent ({exc})") from exc
            if has_text:
                raise ImageRefused(f"this image still shows private text{f' ({what})' if what else ''} after covering faces, "
                                   "plates, cards and documents, so it wasn't sent. Paste the text as a message instead: "
                                   "it's masked there.")
        masked = ImageMasked(chat_id=chat_id, image=buf.getvalue(), width=W, height=H, text=text,
                             sam_images=len(sam_jobs),
                             timings_ms={"spark_find": round(finding.latency_ms), "sam": round(max(sam_ms, default=0))})
        tokens = dict(finding.usage)
        for k, v in refine_usage.items():
            tokens[k] = tokens.get(k, 0) + v

        if verify and not self.vision:
            # No reader re-scans the output; the Glimmer text check (if any) already found no private text in it.
            masked.verify = ({"ok": True, "checked": "no private text left in the masked image (Glimmer check); "
                                                    "faces and objects by SAM 3.1"}
                             if checked else
                             {"ok": None, "skipped": "SAM 3.1 only: there's no reader to re-scan the masked image"})
        elif verify:
            masked.verify, recheck = self._verify(masked.image, regions, W, H)
            masked.timings_ms["spark_recheck"] = round(recheck.latency_ms)
            for k in ("in", "out", "cached_in"):
                tokens[k] = tokens.get(k, 0) + recheck.usage.get(k, 0)
        masked.timings_ms["spark_refine"] = round(refine_ms)
        masked.timings_ms["total"] = round((time.perf_counter() - t0) * 1000)
        cost = run_cost(self.vision.model, tokens, 0) if self.vision else {"usd": 0.0}
        masked.cost = {"spark_usd": cost["usd"], "spark_tokens": tokens,
                       "sam_requests": len(sam_jobs),
                       "note": "SAM 3.1 per-image price is not published; requests are counted, not priced"}
        # Values never leave this function in the response: regions carry labels, the vault keeps the values.
        masked.regions = [{k: v for k, v in r.items() if k != "value"} for r in regions]
        self.vault.audit("image_mask", chat_id, {
            "text": sum(r["kind"] == "text" for r in regions),
            "faces": sum(r["kind"] == "face" for r in regions),
            "other": sum(r["kind"] not in ("text", "face") for r in regions),
        })
        return masked

    def _regions(self, f: Finding, sam_boxes: dict[str, list[Box]], chat_id: str, W: int, H: int) -> list[dict]:
        regions: list[dict] = []
        counters: dict[str, int] = {}

        def visual(kind: str, box: Box, source: str) -> None:
            if any(r["kind"] == kind and Box(*r["box"]).overlap(box) > 0.3 for r in regions):
                return  # already covered by a more precise box
            if kind in BLUR_KINDS:  # faces: grow to hair, ears and chin
                dx, dy = (box.x2 - box.x1) // 6, (box.y2 - box.y1) // 6
                box = Box(max(0, box.x1 - dx), max(0, box.y1 - dy), min(W, box.x2 + dx), min(H, box.y2 + dy))
            counters[kind] = counters.get(kind, 0) + 1
            regions.append({"kind": kind, "type": kind.upper(), "label": f"<{kind.upper()}_{counters[kind]}>",
                            "box": box.as_list(), "source": source})

        source = getattr(self.sam, "model", "sam-3.1")
        for concept, boxes in sam_boxes.items():  # face, license plate, id card, ... -> face, license_plate, id_card
            for b in boxes:
                visual(concept.replace(" ", "_"), b, source)
        for v in f.visual:
            visual(v["kind"], v["box"], self.vision.model)
        for it in f.items:
            label, _ = self.vault.entity_placeholder(chat_id, it["type"], it["text"], placeholder_base(it["type"], None))
            boxes = [it["box"]]
            first = it.get("first_box")
            if first and first.overlap(it["box"]) < 0.3:
                # The two passes disagree on where it is: cover both (one bar if they touch), masking fails safe.
                b = it["box"]
                if first.overlap(b) > 0:
                    boxes = [Box(min(b.x1, first.x1), min(b.y1, first.y1), max(b.x2, first.x2), max(b.y2, first.y2))]
                else:
                    boxes.append(first)
            for b in boxes:
                # Grounded boxes run a few pixels short, mostly sideways: pad wider than tall.
                h = b.y2 - b.y1
                regions.append({"kind": "text", "type": it["type"], "label": label,
                                "box": b.pad(max(6, h * 3 // 5), W, H, max(4, h * 2 // 5)).as_list(),
                                "source": self.vision.model + (" refined" if it.get("refined") else ""), "value": it["text"]})
        return regions

    def _verify(self, image: bytes, regions: list[dict], W: int, H: int) -> tuple[dict, Finding]:
        """Re-scan the output with Muse Spark: masked values must be unreadable, faces must be blurred."""
        try:
            again = self.vision.find(image, "image/png", W, H)
        except BackendError as exc:
            return {"ok": False, "error": str(exc)}, Finding()
        values = {_norm(r["value"]): r["label"] for r in regions if r["kind"] == "text" and len(_norm(r["value"])) >= 4}
        seen = _norm(again.text) + "|" + "|".join(_norm(i["text"]) for i in again.items)
        leaked = sorted({label for v, label in values.items() if v in seen})
        blurred = [Box(*r["box"]) for r in regions if r["kind"] in BLUR_KINDS]
        faces_left = sum(1 for v in again.visual if v["kind"] == "face" and not any(v["box"].overlap(b) > 0.3 for b in blurred))
        # New finds are other text the model now calls sensitive; labels are excluded, since they're ours.
        new = [{"type": i["type"], "text": i["text"]} for i in again.items
               if not re.fullmatch(r"<?[A-Z][A-Z_]*_\d+>?", i["text"].strip()) and _norm(i["text"]) not in values]
        return {"ok": not leaked and not faces_left, "leaked": leaked, "faces_left": faces_left, "new_finds": new}, again
