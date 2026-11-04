import io
import zipfile

from doc_fakes import fake_values
from doc_fixtures import TRICKY_PPTX_VALUES, tricky_pptx
from pptx import Presentation

from muse_shield.app.engine import Masker
from muse_shield.app.vault import Vault
from muse_shield.documents import pptx as X
from muse_shield.documents.ooxml import Package
from muse_shield.documents.pipeline import mask_document
from muse_shield.documents.text import build, flat


def _run(tmp_path):
    vault = Vault(tmp_path / "v.db", b"\x66" * 32)
    return mask_document(tricky_pptx(), Masker(vault, fake_values(TRICKY_PPTX_VALUES)), vault.create_chat())


def test_tricky_pptx_has_no_value_left_anywhere(tmp_path):
    r = _run(tmp_path)
    z = zipfile.ZipFile(io.BytesIO(r.data))
    everything = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    for value in [*TRICKY_PPTX_VALUES, "Headshot of"]:
        assert value not in everything, value
    assert not [n for n in z.namelist() if n.startswith(("ppt/media", "ppt/charts", "ppt/embeddings", "docProps"))
                or "printerSettings" in n]
    codes = {w["code"]: w for w in r.warnings}
    assert codes["hidden_slides"]["where"] == ["slide 2"] and "charts_removed" in codes and "images_removed" in codes


def test_split_runs_group_table_and_notes_are_masked(tmp_path):
    r = _run(tmp_path)
    assert r.missed == 0 and r.pages == 2
    again = build(X.blocks(Package(r.data))).text
    assert flat(again) == flat(r.masked.masked_text)  # unit breaks move when labels change lengths
    assert "Lead: <PERSON_1> (<CONTACT_1>)" in again
    assert "Counsel | <PERSON_2>" in again and "Don't tell <PERSON_2> about the earn-out." in again
    prs = Presentation(io.BytesIO(r.data))  # still opens, notes included
    assert prs.slides[0].notes_slide.notes_text_frame.text == "Don't tell <PERSON_2> about the earn-out."
