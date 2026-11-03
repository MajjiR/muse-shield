"""Synthetic test images with pixel-exact gold: every sensitive value and every harmless line is drawn here,
so its box is known. All data is made up. Card 4111 1111 1111 1111 is the standard Visa test number."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .meta import Box

FONT_PATHS = ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(size: int) -> ImageFont.ImageFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


@dataclass
class Sample:
    name: str
    image: Image.Image
    gold: list[dict] = field(default_factory=list)   # {value, type, box}: must be masked
    keep: list[dict] = field(default_factory=list)   # {text, box}: harmless, should stay readable
    photos: list[Box] = field(default_factory=list)  # ID photos / faces that must be blurred


class Canvas:
    def __init__(self, name: str, w: int, h: int, bg=(248, 248, 246)):
        self.s = Sample(name, Image.new("RGB", (w, h), bg))
        self.d = ImageDraw.Draw(self.s.image)

    def text(self, xy, s: str, size: int = 22, fill=(30, 30, 34)) -> Box:
        f = font(size)
        self.d.text(xy, s, font=f, fill=fill)
        return Box(*[round(v) for v in self.d.textbbox(xy, s, font=f)])

    def line(self, xy, parts: list[tuple[str, str | None]], size: int = 22, fill=(30, 30, 34)) -> None:
        """Draw label/value parts left to right: (text, None) is kept, (text, TYPE) must be masked."""
        x, y = xy
        f = font(size)
        for s, kind in parts:
            box = self.text((x, y), s, size, fill)
            if kind:
                self.s.gold.append({"value": s.strip(), "type": kind, "box": box})
            elif s.strip():
                self.s.keep.append({"text": s.strip(), "box": box})
            x += self.d.textlength(s, font=f)


def id_card() -> Sample:
    c = Canvas("id-card", 900, 560, (233, 237, 242))
    c.d.rounded_rectangle([40, 40, 860, 520], 24, fill=(253, 253, 250), outline=(120, 128, 140), width=3)
    c.line((80, 70), [("RESIDENT IDENTITY CARD", None)], 26)
    # An illustrated portrait (no real face): it is still an ID photo and must be blurred.
    c.d.rectangle([80, 130, 270, 370], fill=(170, 182, 200))
    c.d.ellipse([125, 160, 225, 260], fill=(205, 170, 140))
    c.d.ellipse([105, 270, 245, 420], fill=(90, 110, 160))
    c.d.rectangle([80, 371, 270, 430], fill=(253, 253, 250))
    c.s.photos.append(Box(80, 130, 270, 370))
    c.line((310, 140), [("Name  ", None), ("Ananya Rao", "PERSON")])
    c.line((310, 190), [("Date of birth  ", None), ("14/08/1992", "DATE")])
    c.line((310, 240), [("ID no.  ", None), ("4821 7730 9154", "ID")])
    c.line((310, 290), [("Address  ", None), ("Flat 5B, Lake View Apts, Pune 411001", "ADDRESS")], 20)
    c.line((80, 455), [("IDIND", None), ("RAO", "PERSON"), ("<<", None), ("ANANYA", "PERSON"), ("<<<<<<<", None),
                       ("482177309154", "ID")], 22)
    return c.s


def chat_screenshot() -> Sample:
    c = Canvas("chat-screenshot", 720, 900, (236, 229, 221))
    c.d.rectangle([0, 0, 720, 70], fill=(7, 94, 84))
    c.line((24, 22), [("Vikram Sethi", "PERSON")], 24, (255, 255, 255))
    bubbles = [
        (40, 110, [("Hi, it's ", None), ("Vikram", "PERSON"), (" from the flat viewing", None)]),
        (40, 190, [("My number is ", None), ("+91 98450 22817", "CONTACT")]),
        (40, 270, [("Please send the ", None), ("₹48,500", "AMOUNT"), (" deposit", None)]),
        (40, 350, [("UPI: ", None), ("vikram.sethi@okaxis", "CONTACT")]),
        (40, 430, [("Or card ", None), ("4111 1111 1111 1111", "ID"), (" CVV ", None), ("731", "SECRET")]),
        (40, 510, [("The flat is ", None), ("22 Hill Road, Bandra West, Mumbai", "ADDRESS")]),
    ]
    for x, y, parts in bubbles:
        c.d.rounded_rectangle([x - 16, y - 16, 680, y + 46], 14, fill=(255, 255, 255))
        c.line((x, y), parts, 22)
    c.d.rounded_rectangle([240, 600, 696, 662], 14, fill=(220, 248, 198))
    c.line((256, 616), [("Sounds good, see you Sunday", None)], 22)
    return c.s


def invoice() -> Sample:
    c = Canvas("invoice", 900, 1000, (255, 255, 255))
    c.line((60, 50), [("TAX INVOICE", None)], 34)
    c.line((60, 110), [("Invoice no. ", None), ("INV-2026-0418", "ID")])
    c.line((60, 170), [("Billed to: ", None), ("Meera Krishnan", "PERSON")])
    c.line((60, 210), [("14 Residency Road, Bengaluru 560025", "ADDRESS")])
    c.line((60, 250), [("GSTIN: ", None), ("29AAGCM4821K1Z6", "ID")])
    c.line((60, 290), [("PAN: ", None), ("AAGCM4821K", "ID")])
    c.d.line([60, 350, 840, 350], fill=(200, 200, 200), width=2)
    c.line((60, 370), [("Description", None)], 22)
    c.line((640, 370), [("Amount", None)], 22)
    c.line((60, 420), [("Consulting services, October", None)], 22)
    c.line((640, 420), [("₹1,00,000", "AMOUNT")], 22)
    c.line((60, 470), [("GST 18%", None)], 22)
    c.line((640, 470), [("₹18,000", "AMOUNT")], 22)
    c.d.line([60, 520, 840, 520], fill=(200, 200, 200), width=2)
    c.line((60, 540), [("Total", None)], 26)
    c.line((640, 540), [("₹1,18,000", "AMOUNT")], 26)
    c.line((60, 640), [("Pay to account ", None), ("50100483920117", "ID")])
    c.line((60, 680), [("IFSC ", None), ("HDFC0000521", "ID")])
    c.line((60, 760), [("Thank you for your business", None)], 20)
    return c.s


def terminal() -> Sample:
    c = Canvas("terminal-env", 900, 520, (24, 24, 28))
    c.d.rectangle([0, 0, 900, 40], fill=(48, 48, 56))
    green, white = (126, 224, 129), (220, 220, 225)
    c.line((30, 70), [("$ cat .env", None)], 22, white)
    c.line((30, 120), [("PORT=8080", None)], 22, green)
    c.line((30, 165), [("DB_HOST=", None), ("10.20.3.11", "ID")], 22, green)
    c.line((30, 210), [("DB_PASSWORD=", None), ("Lumen#Prod2026", "SECRET")], 22, green)
    c.line((30, 255), [("API_TOKEN=", None), ("lmn_tok_8f3c21a9e7d4", "SECRET")], 22, green)
    c.line((30, 300), [("STAFF_EMAIL=", None), ("nisha.pillai@lumen.dev", "CONTACT")], 22, green)
    c.line((30, 345), [("LOG_LEVEL=info", None)], 22, green)
    return c.s


def clinic_note() -> Sample:
    c = Canvas("clinic-note", 860, 760, (252, 251, 245))
    c.line((50, 40), [("Clinic notes", None)], 30)
    c.line((50, 110), [("Patient: ", None), ("Rahul Iyer", "PERSON")])
    c.line((50, 155), [("MRN: ", None), ("00482913", "ID")])
    c.line((50, 200), [("DOB: ", None), ("03/11/1979", "DATE")])
    c.line((50, 245), [("Phone: ", None), ("+91 90044 18273", "CONTACT")])
    c.line((50, 310), [("Diagnosis: ", None), ("Type 2 diabetes", "SENSITIVE_ATTRIBUTE")])
    c.line((50, 355), [("Also: ", None), ("HIV positive, on ART", "SENSITIVE_ATTRIBUTE")])
    c.line((50, 420), [("Advice: walk 30 minutes a day", None)])
    c.line((50, 465), [("Follow up in 3 months", None)])
    c.line((50, 560), [("Dr. ", None), ("Kavita Menon", "PERSON")])
    return c.s


SAMPLES = [id_card, chat_screenshot, invoice, terminal, clinic_note]


def all_samples() -> list[Sample]:
    return [make() for make in SAMPLES]
