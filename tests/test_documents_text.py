import io

from docx import Document

from muse_shield.app.engine import paragraphs
from muse_shield.documents.ooxml import Package
from muse_shield.documents.text import Atom, Block, build, splice


class El:  # a stand-in for an XML text element
    def __init__(self, text):
        self.text = text


def _block(*parts, where="p", hard=False):
    return Block([Atom(t, El(t)) if not t.startswith("|") else Atom("\t", El("\t"), "sep") for t in parts], where, hard)


def test_atoms_map_back_to_text():
    dt = build([_block("Arjun ", "Mal", "hotra"), _block("Salary"), _block("Slide 2", hard=True)])
    for a in dt.atoms:
        assert dt.text[a.start:a.end] == a.text
    assert dt.text == "Arjun Malhotra\nSalary\n\nSlide 2"
    assert [u[0] for u in dt.units] == [o for o, _ in paragraphs(dt.text)]
    assert [(a.text, lo, hi) for a, lo, hi in dt.locate(4, 10)] == [("Arjun ", 4, 6), ("Mal", 0, 3), ("hotra", 0, 1)]


def test_packing_limits_calls():
    blocks = [_block(f"Line {i} of the contract with some words in it.") for i in range(600)]
    assert len(build(blocks).units) < 40  # 28k characters in 800-character units
    assert len(build(blocks, max_chars=0).units) == 600


def test_blank_line_inside_a_block_is_collapsed():
    b = Block([Atom("Name", El("Name")), Atom("\n", El("br"), "sep"), Atom("\n", El("br"), "sep"), Atom("Rohan", El("Rohan"))], "p")
    dt = build([b])
    assert dt.text == "Name\n Rohan" and len(dt.units) == 1


def test_splice_puts_label_in_first_run_and_empties_the_rest():
    blocks = [_block("Dear Arjun ", "Mal", "hotra, welcome", "|tab", "x")]
    dt = build(blocks)
    s = dt.text.index("Arjun")
    e = s + len("Arjun Malhotra")
    removed = []
    missed = splice(dt, [(s, e, "<PERSON_1>")], lambda a, v: setattr(a.ref, "text", v), removed.append)
    assert missed == 0
    assert [a.ref.text for a in blocks[0].atoms[:3]] == ["Dear <PERSON_1>", "", ", welcome"]


def test_package_drop_part_cleans_rels_and_types():
    buf = io.BytesIO()
    d = Document()
    d.add_paragraph("x")
    d.save(buf)
    pkg = Package(buf.getvalue())
    assert pkg.has("docProps/core.xml")
    pkg.drop_part("docProps/core.xml")
    out = Package(pkg.save())
    assert not out.has("docProps/core.xml")
    assert "core.xml" not in out.blobs["_rels/.rels"].decode()
    assert "core.xml" not in out.blobs["[Content_Types].xml"].decode()
    Document(io.BytesIO(pkg.save()))  # still opens
