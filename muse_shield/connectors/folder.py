"""Your documents folder: browse it, read any file in it, and calculate over its tables on this device.

The root is MUSE_SHIELD_FILES (or <MUSE_SHIELD_DATA_DIR>/files, else the bundled samples). Every file and
folder is addressed by an opaque id from list_folder or search_files, never by a path, so a model
can't name anything outside the root and no file name leaks through an id.

query_table is the calculator for tables: it filters, groups and adds up a CSV (or every CSV in a
folder, e.g. twelve monthly statements) here, and only the totals leave the function, each as a new
<RESULT_n> placeholder. The model never needs to read every row, and never sees a number.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from ..app.vault import Vault
from . import data_path, matches, opaque_id
from .compute import fmt

MAX_TEXT = 2000  # characters of a document the model gets; each paragraph costs one masking call
SAMPLE_ROWS = 5
MAX_DEPTH = 4
TEXT = {".md", ".txt"}
TABLE = {".csv", ".tsv"}
DOCS = {".pdf", ".docx", ".pptx"}
OPERATIONS = ("sum", "average", "count", "min", "max")
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def root() -> Path:
    return data_path("files", "MUSE_SHIELD_FILES").expanduser().resolve()


def _kind(p: Path) -> str | None:
    if p.is_dir():
        return "folder"
    s = p.suffix.lower()
    return "text" if s in TEXT else "table" if s in TABLE else s[1:] if s in DOCS else None


def _entries() -> dict[str, Path]:
    """id -> path for every supported file and folder under the root (no hidden files, no symlinks out)."""
    base, out = root(), {}
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base)
        if any(part.startswith(".") for part in rel.parts) or len(rel.parts) > MAX_DEPTH or p.is_symlink():
            continue
        if _kind(p):
            out[opaque_id(str(rel))] = p
    return out


def _find(entry_id: str, *, folder: bool | None = None) -> Path:
    p = _entries().get(entry_id)
    if p is None or (folder is True and not p.is_dir()) or (folder is False and p.is_dir()):
        raise ValueError(f"no {'folder' if folder else 'file'} with id {entry_id}; use list_folder or search_files")
    return p


def _label(p: Path) -> str:
    return p.stem.replace("_", " ").replace("-", " ") if p.is_file() else p.name.replace("_", " ")


def text_of(p: Path) -> str:
    """Plain text of a document. PDF, Word and PowerPoint go through the document extractors."""
    kind = _kind(p)
    if kind == "text":
        return p.read_text(errors="replace")
    if kind == "table":
        return p.read_text(errors="replace")
    from ..documents import pdf, pptx, docx  # optional extra; imported only when such a file is read
    from ..documents.text import build

    module = {"pdf": pdf, "docx": docx, "pptx": pptx}[kind]
    return build(module.blocks(module.load(p.read_bytes()))).text


# -- browse and read ---------------------------------------------------------------------------
def list_folder(vault: Vault, chat_id: str, args: dict) -> dict:
    base = _find(args["folder_id"], folder=True) if args.get("folder_id") else root()
    out = []
    for eid, p in _entries().items():
        if p.parent == base:
            entry = {"id": eid, "name": _label(p), "kind": _kind(p)}
            if p.is_dir():
                entry["items"] = str(sum(1 for q in _entries().values() if q.parent == p))
            out.append(entry)
    out.sort(key=lambda e: (e["kind"] != "folder", e["name"].casefold()))
    return {"status": f"{len(out)} items", "entries": out}


def search_files(vault: Vault, chat_id: str, args: dict) -> dict:
    out = []
    for eid, p in _entries().items():
        if p.is_dir():
            continue
        try:
            text = text_of(p)
        except Exception:  # an unreadable file is skipped, not fatal
            continue
        if matches(args.get("query"), _label(p), text):
            out.append({"id": eid, "name": _label(p), "kind": _kind(p), "excerpt": text[:300]})
    return {"status": f"{len(out[:10])} files", "files": out[:10]}


def read_file(vault: Vault, chat_id: str, args: dict) -> dict:
    p = _find(args["file_id"], folder=False)
    if _kind(p) == "table":
        header, rows = _table(p)
        sample = [" · ".join(f"{k}: {v}" for k, v in r.items()) for r in rows[:SAMPLE_ROWS]]
        return {"status": f"table with {len(rows)} rows; use query_table to calculate over it", "id": args["file_id"],
                "name": _label(p), "columns": ", ".join(header), "rows": str(len(rows)),
                "sample": [{"id": str(i), "row": s} for i, s in enumerate(sample)]}
    text = text_of(p)
    return {"status": "read" + (" (trimmed)" if len(text) > MAX_TEXT else ""), "id": args["file_id"],
            "name": _label(p), "text": text[:MAX_TEXT]}


# -- calculate over tables ---------------------------------------------------------------------
def _table(p: Path) -> tuple[list[str], list[dict]]:
    text = p.read_text(errors="replace")
    dialect = "excel-tab" if p.suffix.lower() == ".tsv" else "excel"
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    return [h.strip() for h in reader.fieldnames or []], rows


def _number(cell: str) -> float | None:
    m = NUMBER.search(cell.replace("₹", "").replace("$", ""))
    return float(m.group(0).replace(",", "")) if m else None


def _currency(header: str, cells: list[str]) -> str:
    h = header.casefold()
    if "₹" in header or "inr" in h or "rs" in h.split() or any("₹" in c for c in cells[:20]):
        return "₹"
    if "$" in header or "usd" in h or any("$" in c for c in cells[:20]):
        return "$"
    return ""


def _column(header: list[str], wanted: str | None, where: str) -> str:
    if not wanted:
        raise ValueError(f"{where} is required; columns: {', '.join(header)}")
    for h in header:
        if h.casefold() == wanted.casefold():
            return h
    hits = [h for h in header if wanted.casefold() in h.casefold()]
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"no column '{wanted}'; columns: {', '.join(header)}")


def query_table(vault: Vault, chat_id: str, args: dict) -> dict:
    """Filter, group and aggregate one table, or every table in a folder that shares its columns."""
    target = _find(args["source_id"])
    files = sorted(q for q in _entries().values() if q.parent == target and _kind(q) == "table") if target.is_dir() else [target]
    if not files or any(_kind(f) != "table" for f in files):
        raise ValueError("query_table works on a CSV file, or a folder of CSV files")
    header, rows = _table(files[0])
    for f in files[1:]:
        h, more = _table(f)
        if [c.casefold() for c in h] != [c.casefold() for c in header]:
            raise ValueError(f"{_label(f)} has different columns from {_label(files[0])}")
        rows += more

    op = (args.get("operation") or "sum").lower()
    if op not in OPERATIONS:
        raise ValueError(f"operation must be one of {', '.join(OPERATIONS)}")
    value_col = _column(header, args.get("column"), "column") if op != "count" else None
    if args.get("contains"):
        cols = [_column(header, args["contains_column"], "contains_column")] if args.get("contains_column") else header
        rows = [r for r in rows if all(any(w in r[c].casefold() for c in cols) for w in args["contains"].casefold().split())]
    if args.get("month"):
        rows = [r for r in rows if any(r[c].startswith(args["month"]) for c in header if "date" in c.casefold())]

    currency = _currency(value_col, [r[value_col] for r in rows]) if value_col else ""
    group_col = _column(header, args["group_by"], "group_by") if args.get("group_by") else None
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r[group_col] if group_col else "", []).append(r)

    def aggregate(rs: list[dict]) -> str:
        if op == "count":
            return str(len(rs))
        nums = [n for n in (_number(r[value_col]) for r in rs) if n is not None]
        if not nums:
            return "no numbers"
        value = {"sum": sum(nums), "average": sum(nums) / len(nums), "min": min(nums), "max": max(nums)}[op]
        shown = fmt(value, currency)
        vault.entity_placeholder(chat_id, "AMOUNT", shown, base="RESULT")  # becomes <RESULT_n> before any agent sees it
        return shown

    status = f"{op} over {len(rows)} rows from {len(files)} file{'s' if len(files) > 1 else ''}, computed on this device"
    if not group_col:
        return {"status": status, "result": aggregate(rows)}
    out = sorted(({"group": g, "value": aggregate(rs), "count": str(len(rs))} for g, rs in groups.items()),
                 key=lambda e: -(_number(e["value"]) or 0) if op != "count" else -int(e["value"]))
    return {"status": status, "groups": out[:25]}
