"""Drawing the masks: faces blurred inside a feathered oval, values covered and labelled with their placeholder."""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .meta import Box

COVER = (24, 24, 27)      # text covers: near-black, like a redaction bar
LABEL = (250, 250, 250)
LABEL_ON_DARK = (228, 228, 231)  # the bar on dark backgrounds


def blur_oval(img: Image.Image, box: Box) -> None:
    """Blur hard enough that a face can't be recognised, fading out at the edge of an oval."""
    w, h = box.x2 - box.x1, box.y2 - box.y1
    if w < 2 or h < 2:
        return
    region = img.crop(box.as_list())
    radius = max(6, max(w, h) // 5)
    blurred = region.filter(ImageFilter.GaussianBlur(radius)).filter(ImageFilter.GaussianBlur(radius))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, w - 1, h - 1], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(1, min(w, h) // 12)))
    region.paste(blurred, (0, 0), mask)
    img.paste(region, (box.x1, box.y1))


def pixelate(img: Image.Image, box: Box, cells: int = 8) -> None:
    w, h = box.x2 - box.x1, box.y2 - box.y1
    if w < 2 or h < 2:
        return
    region = img.crop(box.as_list()).resize((max(1, w // max(1, w // cells)), max(1, h // max(1, h // cells))), Image.BILINEAR)
    img.paste(region.resize((w, h), Image.NEAREST), (box.x1, box.y1))


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def cover(img: Image.Image, box: Box, label: str, background: Image.Image | None = None) -> None:
    """A solid bar over the value with its placeholder written on it, shrunk to fit. On a dark
    background (a terminal, a dark-mode screenshot) the bar is light, so it reads as masked, not blank.
    Pass the unmasked image as background so earlier bars don't decide the colour."""
    draw = ImageDraw.Draw(img)
    gray = (background or img).crop(box.as_list()).convert("L").resize((1, 1), Image.BOX).getpixel((0, 0))
    fill, ink = (COVER, LABEL) if gray >= 110 else (LABEL_ON_DARK, COVER)
    draw.rectangle(box.as_list(), fill=fill)
    w, h = box.x2 - box.x1, box.y2 - box.y1
    size = max(8, min(int(h * 0.72), 28))
    while size > 8:
        font = _font(size)
        if draw.textlength(label, font=font) <= w - 4:
            break
        size -= 1
    font = _font(size)
    if draw.textlength(label, font=font) <= w + 2 and size <= h + 2:
        draw.text((box.x1 + w / 2, box.y1 + h / 2), label, fill=ink, font=font, anchor="mm")
