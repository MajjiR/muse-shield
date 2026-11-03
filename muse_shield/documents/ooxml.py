"""A small Open Packaging (OPC) layer for .docx and .pptx: parts, content types and relationships.

We work on the raw package rather than python-docx/python-pptx objects because masking has to reach
every part (headers, footnotes, notes, layouts, docProps) and remove parts cleanly.
"""

from __future__ import annotations

import io
import posixpath
import zipfile

from lxml import etree

CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)


def rels_name(part: str) -> str:
    d, f = posixpath.split(part)
    return posixpath.join(d, "_rels", f + ".rels")


def part_of_rels(rels: str) -> str:
    d, f = posixpath.split(rels)
    return posixpath.join(posixpath.dirname(d), f[: -len(".rels")])


class Package:
    def __init__(self, data: bytes):
        z = zipfile.ZipFile(io.BytesIO(data))
        self.order = [i.filename for i in z.infolist() if not i.is_dir()]
        self.blobs = {n: z.read(n) for n in self.order}
        self._xml: dict[str, etree._Element] = {}

    # --- parts -----------------------------------------------------------------------------------------
    def has(self, name: str) -> bool:
        return name in self.blobs

    def xml(self, name: str) -> etree._Element:
        if name not in self._xml:
            self._xml[name] = etree.fromstring(self.blobs[name], _PARSER)
        return self._xml[name]

    def is_xml(self, name: str) -> bool:
        return name.endswith((".xml", ".rels")) or "xml" in self.content_type(name)

    def names(self) -> list[str]:
        return list(self.order)

    def content_type(self, name: str) -> str:
        ct = self.xml("[Content_Types].xml")
        for o in ct.iterfind(f"{{{CT_NS}}}Override"):
            if o.get("PartName", "").lstrip("/").lower() == name.lower():
                return o.get("ContentType", "")
        ext = name.rsplit(".", 1)[-1].lower()
        for d in ct.iterfind(f"{{{CT_NS}}}Default"):
            if d.get("Extension", "").lower() == ext:
                return d.get("ContentType", "")
        return ""

    def parts_with_type(self, fragment: str) -> list[str]:
        return [n for n in self.order if fragment in self.content_type(n)]

    # --- relationships ---------------------------------------------------------------------------------
    def rels(self, part: str) -> list[etree._Element]:
        rn = rels_name(part)
        return list(self.xml(rn).iterfind(f"{{{REL_NS}}}Relationship")) if rn in self.blobs else []

    def target(self, part: str, rel: etree._Element) -> str | None:
        """The package part a relationship points to, or None for an external target."""
        if rel.get("TargetMode") == "External":
            return None
        t = rel.get("Target", "")
        if t.startswith("/"):
            return t.lstrip("/")
        return posixpath.normpath(posixpath.join(posixpath.dirname(part), t))

    def related(self, part: str, type_suffix: str) -> list[str]:
        return [t for r in self.rels(part) if r.get("Type", "").endswith(type_suffix) and (t := self.target(part, r)) and t in self.blobs]

    def drop_rel(self, part: str, rel: etree._Element) -> None:
        rel.getparent().remove(rel)

    def drop_part(self, name: str) -> None:
        """Remove a part, its content-type override, its own rels, and every relationship pointing to it.
        Parts only it referenced are removed too (a chart's embedded workbook, an image's thumbnail)."""
        if name not in self.blobs:
            return
        children = [t for r in self.rels(name) if (t := self.target(name, r))]
        for n in (name, rels_name(name)):
            self.blobs.pop(n, None)
            self._xml.pop(n, None)
            if n in self.order:
                self.order.remove(n)
        ct = self.xml("[Content_Types].xml")
        for o in list(ct.iterfind(f"{{{CT_NS}}}Override")):
            if o.get("PartName", "").lstrip("/").lower() == name.lower():
                ct.remove(o)
        for rn in [n for n in self.order if n.endswith(".rels")]:
            src = part_of_rels(rn) if not rn.startswith("_rels/") else ""
            for r in list(self.xml(rn).iterfind(f"{{{REL_NS}}}Relationship")):
                if self.target(src, r) == name:
                    r.getparent().remove(r)
        for child in children:
            if child in self.blobs and not self.referenced(child):
                self.drop_part(child)

    def referenced(self, name: str) -> bool:
        for rn in (n for n in self.order if n.endswith(".rels")):
            src = part_of_rels(rn) if not rn.startswith("_rels/") else ""
            if any(self.target(src, r) == name for r in self.xml(rn).iterfind(f"{{{REL_NS}}}Relationship")):
                return True
        return False

    def rel_ids(self, part: str) -> set[str]:
        return {r.get("Id") for r in self.rels(part)}

    # --- output ----------------------------------------------------------------------------------------
    def save(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for n in self.order:
                data = etree.tostring(self._xml[n], xml_declaration=True, encoding="UTF-8", standalone=True) if n in self._xml else self.blobs[n]
                z.writestr(n, data)
        return buf.getvalue()


def qn(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def unwrap(el: etree._Element) -> None:
    """Replace an element by its children (keeps the text runs of a hyperlink or an insertion)."""
    parent = el.getparent()
    if parent is None:
        return
    i = parent.index(el)
    for child in list(el):
        parent.insert(i, child)
        i += 1
    parent.remove(el)


def remove(el: etree._Element) -> None:
    if el.getparent() is not None:
        el.getparent().remove(el)
