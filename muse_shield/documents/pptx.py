"""PowerPoint (.pptx): sanitize what can't be masked reliably, extract text atoms, write placeholders back."""

from __future__ import annotations

from collections import Counter

from lxml import etree

from .docx import metadata as _metadata
from .ooxml import R_NS, REL_NS, Package, part_of_rels, qn, remove
from .text import Atom, Block, DocText, remove_xml, set_xml_text, splice

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
DOC_REL = "/officeDocument"
TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"

DROP_REL_TYPES = ("/image", "/chart", "/diagramData", "/diagramLayout", "/diagramQuickStyle", "/diagramColors",
                  "/diagramDrawing", "/oleObject", "/package", "/video", "/audio", "/media", "/hdphoto", "/tags",
                  "/comments", "/commentAuthors", "/authors", "/thumbnail", "/custom-properties", "/core-properties",
                  "/extended-properties", "/hyperlink", "/font", "/customXml", "/vbaProject")
DROP_TYPES = ("image/", "video/", "audio/", "drawingml.chart", "drawingml.diagram", "oleObject", "spreadsheetml",
              "chartstyle", "chartcolorstyle", "presentationml.tags", "comments", "commentAuthors", "authors",
              "x-font", "obfuscatedFont", "custom-properties", "core-properties", "extended-properties", "customXml",
              "printerSettings")

def p(tag: str) -> str:
    return qn(P, tag)


def a(tag: str) -> str:
    return qn(A, tag)


def load(data: bytes) -> Package:
    return Package(data)


def main_part(pkg: Package) -> str:
    return pkg.related("", DOC_REL)[0]


def slides(pkg: Package) -> list[str]:
    """Slides in presentation order."""
    pres = main_part(pkg)
    by_id = {r.get("Id"): pkg.target(pres, r) for r in pkg.rels(pres)}
    lst = pkg.xml(pres).find(p("sldIdLst"))
    return [by_id[s.get(qn(R_NS, "id"))] for s in (lst if lst is not None else []) if by_id.get(s.get(qn(R_NS, "id")))]


def text_parts(pkg: Package) -> list[tuple[str, str]]:
    out = []
    for i, s in enumerate(slides(pkg), 1):
        out.append((s, f"slide {i}"))
        out += [(n, f"slide {i} notes") for n in pkg.related(s, "/notesSlide")]
    pres = main_part(pkg)
    masters = pkg.related(pres, "/slideMaster")
    layouts = sorted({lay for m in masters for lay in pkg.related(m, "/slideLayout")})
    out += [(lay, f"layout {i}") for i, lay in enumerate(layouts, 1)]
    out += [(m, f"master {i}") for i, m in enumerate(masters, 1)]
    out += [(m, "notes master") for m in pkg.related(pres, "/notesMaster")]
    out += [(m, "handout master") for m in pkg.related(pres, "/handoutMaster")]
    return out


def pages(pkg: Package) -> int:
    return len(slides(pkg))


def metadata(pkg: Package) -> list[str]:
    return _metadata(pkg)


def sanitize(pkg: Package) -> list[dict]:
    n: Counter = Counter()
    where: dict[str, list[str]] = {}
    for part, label in text_parts(pkg):
        root = pkg.xml(part)
        if root.tag == p("sld") and root.get("show") == "0":
            n["hidden_slides"] += 1
            where.setdefault("hidden_slides", []).append(label)
        for el in list(root.iter(p("pic"))):
            n["images_removed"] += 1
            where.setdefault("images_removed", []).append(label)
            remove(el)
        for el in list(root.iter(a("blipFill"))):
            el.getparent().replace(el, etree.Element(a("noFill")))
            n["images_removed"] += 1
        for el in list(root.iter(p("bg"))):
            if el.find(f".//{{{A}}}blip") is not None:
                remove(el)
                n["images_removed"] += 1
        for frame in list(root.iter(p("graphicFrame"))):
            gd = frame.find(f".//{{{A}}}graphicData")
            if gd is None or gd.get("uri") != TABLE_URI:
                n["charts_removed"] += 1
                where.setdefault("charts_removed", []).append(label)
                remove(frame)
        for tag in ("hlinkClick", "hlinkMouseOver", "hlinkHover"):  # links point at addresses or files
            for el in list(root.iter(a(tag))):
                if el.get(qn(R_NS, "id")):
                    n["links_removed"] += 1
                    remove(el)
        for i, el in enumerate(root.iter(p("cNvPr")), 1):
            el.set("descr", "")
            el.set("title", "")
            el.set("name", f"Shape {i}")
        for el in list(root.iter(p("custDataLst"))):
            remove(el)
        for c in pkg.related(part, "/comments"):
            n["comments_removed"] += len(list(pkg.xml(c))) if pkg.has(c) else 0
    pres = pkg.xml(main_part(pkg))
    for el in list(pres.iter()):
        if isinstance(el.tag, str) and el.tag.rsplit("}", 1)[-1] in ("sectionLst", "custShowLst", "custDataLst"):
            remove(el)
    _drop_parts(pkg)
    return [{"code": code, "count": count, **({"where": sorted(set(where[code]))} if code in where else {})}
            for code, count in n.items() if count]


def _drop_parts(pkg: Package) -> None:
    for name in list(pkg.names()):
        if not name.endswith(".rels") or not pkg.has(name):
            continue
        src = part_of_rels(name) if not name.startswith("_rels/") else ""
        for rel in list(pkg.xml(name).iterfind(qn(REL_NS, "Relationship"))):
            if rel.get("Type", "").endswith(DROP_REL_TYPES):
                t = pkg.target(src, rel)
                rel.getparent().remove(rel)
                if t and pkg.has(t) and not pkg.referenced(t):
                    pkg.drop_part(t)
    for name in list(pkg.names()):
        if name.endswith(".rels") or name == "[Content_Types].xml" or not pkg.has(name):
            continue
        if name.startswith(("ppt/media/", "ppt/embeddings/", "ppt/charts/", "ppt/diagrams/", "ppt/tags/", "ppt/comments/",
                            "customXml/", "docProps/")) or any(f in pkg.content_type(name) for f in DROP_TYPES):
            pkg.drop_part(name)


def _owner(el: etree._Element, tag: str) -> etree._Element | None:
    q = el.getparent()
    while q is not None and q.tag != tag:
        q = q.getparent()
    return q


def blocks(pkg: Package) -> list[Block]:
    out: list[Block] = []
    for part, where in text_parts(pkg):
        root = pkg.xml(part)
        rows: dict[int, Block] = {}
        last_cell: dict[int, etree._Element] = {}
        for para in root.iter(a("p")):
            atoms = []
            for el in para.iter(a("t"), a("br")):
                atoms.append(Atom(el.text or "", el) if el.tag == a("t") else Atom("\n", el, "sep"))
            if not "".join(x.text for x in atoms).strip():
                continue
            tr = _owner(para, a("tr"))
            if tr is None:
                out.append(Block(atoms, where))
                continue
            tc = _owner(para, a("tc"))
            row = rows.get(id(tr))
            if row is None:
                row = rows[id(tr)] = Block([], where)
                out.append(row)
            else:
                row.atoms.append(Atom(" / " if last_cell.get(id(tr)) is tc else " | ", kind="synthetic"))
            last_cell[id(tr)] = tc
            row.atoms += atoms
    return out


def apply(pkg: Package, dt: DocText, replacements: list[tuple[int, int, str]]) -> int:
    return splice(dt, replacements, set_xml_text, remove_xml)


def save(pkg: Package) -> bytes:
    return pkg.save()
