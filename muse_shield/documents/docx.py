"""Word (.docx): sanitize what can't be masked reliably, extract text atoms, write placeholders back."""

from __future__ import annotations

from collections import Counter

from lxml import etree

from .ooxml import REL_NS, Package, part_of_rels, qn, remove, unwrap
from .text import Atom, Block, DocText, remove_xml, set_xml_text, splice

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
V = "urn:schemas-microsoft-com:vml"
DOC_REL = "/officeDocument"

# Parts that carry content we remove rather than mask (by content type fragment).
DROP_TYPES = ("image/", "video/", "audio/", "drawingml.chart", "drawingml.diagram", "oleObject", "spreadsheetml",
              "chartstyle", "chartcolorstyle", "obfuscatedFont", "x-font", "customXmlProperties", "glossary",
              "comments", "people", "custom-properties", "core-properties", "extended-properties", "printerSettings")
DROP_REL_TYPES = ("/image", "/chart", "/diagramData", "/diagramLayout", "/diagramQuickStyle", "/diagramColors",
                  "/diagramDrawing", "/oleObject", "/package", "/video", "/audio", "/media", "/hdphoto", "/customXml",
                  "/glossaryDocument", "/comments", "/commentsExtended", "/commentsIds", "/commentsExtensible",
                  "/people", "/font", "/thumbnail", "/custom-properties", "/core-properties", "/extended-properties",
                  "/attachedTemplate", "/hyperlink", "/subDocument", "/aFChunk", "/frame")
TEXT_RELS = (("/header", "header"), ("/footer", "footer"), ("/footnotes", "footnotes"), ("/endnotes", "endnotes"))


def w(tag: str) -> str:
    return qn(W, tag)


def main_part(pkg: Package) -> str:
    return next(t for t in pkg.related("", DOC_REL))


def text_parts(pkg: Package) -> list[tuple[str, str]]:
    main = main_part(pkg)
    out = [(main, "body")]
    for suffix, where in TEXT_RELS:
        out += [(p, where) for p in pkg.related(main, suffix)]
    return out


META_FIELDS = {"docProps/core.xml": ("creator", "lastModifiedBy", "title", "subject", "keywords", "description", "category"),
               "docProps/app.xml": ("Company", "Manager", "HyperlinkBase"),
               "docProps/custom.xml": ("lpwstr", "lpstr", "bstr")}


def metadata(pkg: Package) -> list[str]:
    """Identifying values in document properties, captured before they're removed (for the verifier)."""
    vals = []
    for part, fields in META_FIELDS.items():
        if pkg.has(part):
            vals += [el.text.strip() for el in pkg.xml(part).iter() if isinstance(el.tag, str)
                     and el.tag.rsplit("}", 1)[-1] in fields and el.text and len(el.text.strip()) >= 3]
    return vals


def sanitize(pkg: Package) -> list[dict]:
    """Remove what we can't mask reliably, so Spark never sees it and the copy doesn't keep it."""
    n: Counter = Counter()
    for part, _ in text_parts(pkg):
        root = pkg.xml(part)
        # Tracked changes: accept them all.
        for tag in ("del", "moveFrom", "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
                    "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange", "tcPrChange",
                    "tblGridChange", "numberingChange", "cellIns", "cellDel", "cellMerge", "customXmlInsRangeStart",
                    "customXmlInsRangeEnd", "customXmlDelRangeStart", "customXmlDelRangeEnd"):
            for el in list(root.iter(w(tag))):
                n["tracked_changes_accepted"] += tag in ("del", "moveFrom")
                remove(el)
        for tag in ("ins", "moveTo"):
            for el in list(root.iter(w(tag))):
                n["tracked_changes_accepted"] += 1
                unwrap(el)
        # Comments (their parts are dropped below).
        for tag in ("commentRangeStart", "commentRangeEnd"):
            for el in list(root.iter(w(tag))):
                remove(el)
        for ref in list(root.iter(w("commentReference"))):
            n["comments_removed"] += 1
            run = ref.getparent()
            remove(run if run is not None and run.tag == w("r") and len(run.findall(w("t"))) == 0 else ref)
        # Field codes: keep what the field shows, drop the instructions (HYPERLINK "mailto:…", MERGEFIELD…).
        depth_instr: list[bool] = []
        for run in list(root.iter(w("r"))):
            fc = run.find(w("fldChar"))
            kind = fc.get(w("fldCharType")) if fc is not None else None
            if kind == "begin":
                depth_instr.append(True)
                n["fields_unlinked"] += 1
                remove(run)
            elif kind == "separate" and depth_instr:
                depth_instr[-1] = False
                remove(run)
            elif kind == "end" and depth_instr:
                depth_instr.pop()
                remove(run)
            elif any(depth_instr):
                remove(run)
        for el in list(root.iter(w("instrText"), w("delInstrText"))):
            remove(el)
        for el in list(root.iter(w("fldSimple"))):
            n["fields_unlinked"] += 1
            unwrap(el)
        # Links and bookmarks (bookmark names can be "_Arjun_Malhotra").
        for el in list(root.iter(w("hyperlink"))):
            n["links_removed"] += 1
            unwrap(el)
        for tag in ("bookmarkStart", "bookmarkEnd"):
            for el in list(root.iter(w(tag))):
                remove(el)
        # Text boxes exist twice (DrawingML choice + VML fallback): keep one copy.
        for el in list(root.iter(qn(MC, "Fallback"))):
            remove(el)
        # Pictures, charts, SmartArt, OLE objects, watermarks.
        for el in list(root.iter(w("drawing"))):
            if el.find(f".//{{{WPS}}}txbx") is None or el.find(f".//{{{A}}}blip") is not None:
                n["images_removed"] += 1
                remove(el)
        for el in list(root.iter(w("pict"))):
            if el.find(f".//{{{V}}}textbox") is None or el.find(f".//{{{V}}}imagedata") is not None:
                n["images_removed"] += 1
                remove(el)
        for tag in ("object", "altChunk", "subDoc"):
            for el in list(root.iter(w(tag))):
                n["embedded_removed"] += 1
                remove(el)
        for el in list(root.iter(w("background"), w("dataBinding"))):
            remove(el)
        # Alt text and names on the drawings that are left (text boxes).
        for i, el in enumerate(root.iter(qn(WP, "docPr")), 1):
            el.set("descr", "")
            el.set("title", "")
            el.set("name", f"Shape {i}")
    # Settings: mail-merge sources, template paths, document variables.
    for part in pkg.related(main_part(pkg), "/settings"):
        root = pkg.xml(part)
        for tag in ("docVars", "mailMerge", "attachedTemplate", "rsids"):
            for el in list(root.iter(w(tag))):
                remove(el)
    # Embedded fonts.
    for part in pkg.related(main_part(pkg), "/fontTable"):
        for tag in ("embedRegular", "embedBold", "embedItalic", "embedBoldItalic"):
            for el in list(pkg.xml(part).iter(w(tag))):
                remove(el)
    _drop_parts(pkg, n)
    return [{"code": code, "count": count} for code, count in n.items() if count]


def _drop_parts(pkg: Package, n: Counter) -> None:
    for name in list(pkg.names()):
        if not name.endswith(".rels") or not pkg.has(name):
            continue
        for rel in list(pkg.xml(name).iterfind(qn(REL_NS, "Relationship"))):
            if rel.get("Type", "").endswith(DROP_REL_TYPES):
                src = part_of_rels(name) if not name.startswith("_rels/") else ""
                t = pkg.target(src, rel)
                rel.getparent().remove(rel)
                if t and pkg.has(t) and not pkg.referenced(t):
                    pkg.drop_part(t)
    for name in list(pkg.names()):
        if name.endswith(".rels") or name == "[Content_Types].xml":
            continue
        if name.startswith(("customXml/", "word/media/", "word/embeddings/", "word/charts/", "word/diagrams/", "word/glossary/", "word/fonts/")) \
                or any(f in pkg.content_type(name) for f in DROP_TYPES):
            if pkg.has(name):
                pkg.drop_part(name)


def _owner(el: etree._Element, tag: str) -> etree._Element | None:
    p = el.getparent()
    while p is not None and p.tag != tag:
        p = p.getparent()
    return p


def blocks(pkg: Package) -> list[Block]:
    out: list[Block] = []
    for part, where in text_parts(pkg):
        root = pkg.xml(part)
        first = True
        rows: dict[int, Block] = {}
        last_cell: dict[int, etree._Element] = {}
        for p in root.iter(w("p")):
            atoms: list[Atom] = []
            for el in p.iter(w("t"), w("tab"), w("br"), w("cr"), w("noBreakHyphen")):
                if _owner(el, w("p")) is not p:
                    continue
                if el.tag == w("t"):
                    atoms.append(Atom(el.text or "", el))
                elif el.tag == w("tab"):
                    if el.getparent() is not None and el.getparent().tag == w("r"):
                        atoms.append(Atom("\t", el, "sep"))
                elif el.tag == w("noBreakHyphen"):
                    atoms.append(Atom("-", el, "sep"))
                else:
                    atoms.append(Atom("\n", el, "sep"))
            if not "".join(a.text for a in atoms).strip():
                continue
            tr = _owner(p, w("tr"))
            if tr is not None:
                tc = _owner(p, w("tc"))
                row = rows.get(id(tr))
                if row is None:
                    row = rows[id(tr)] = Block([], where, hard=first)
                    out.append(row)
                elif tc is not None and last_cell.get(id(tr)) is tc:
                    row.atoms.append(Atom(" / ", kind="synthetic"))
                else:
                    row.atoms.append(Atom(" | ", kind="synthetic"))
                last_cell[id(tr)] = tc
                row.atoms += atoms
            else:
                out.append(Block(atoms, where, hard=first))
            first = False
    return out


def apply(pkg: Package, dt: DocText, replacements: list[tuple[int, int, str]]) -> int:
    return splice(dt, replacements, set_xml_text, remove_xml)


def save(pkg: Package) -> bytes:
    return pkg.save()




def load(data: bytes) -> Package:
    return Package(data)


def pages(pkg: Package) -> int:
    """Word has no fixed pages; report sections as a rough size."""
    return max(1, len(list(pkg.xml(main_part(pkg)).iter(w("sectPr")))))
