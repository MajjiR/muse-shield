"""Made-up Word, PowerPoint and PDF files that exercise the hard cases."""

import io

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml
from PIL import Image

NSW = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def png() -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (200, 30, 30)).save(buf, "PNG")
    buf.seek(0)
    return buf


def tricky_docx() -> bytes:
    d = Document()
    d.core_properties.author = "Meera Pillai"
    d.core_properties.last_modified_by = "Meera Pillai"
    d.core_properties.title = "Offer for Arjun Malhotra"
    d.sections[0].header.paragraphs[0].text = "Confidential: prepared for Arjun Malhotra"
    d.sections[0].footer.paragraphs[0].text = "Call 98450 12345 with questions"

    p = d.add_paragraph("Dear ")
    p.add_run("Arjun ").bold = True
    p.add_run("Mal").italic = True
    p.add_run("hotra, welcome to Kestrel Labs.")

    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Salary", "₹28 lakh"
    t.cell(1, 0).text, t.cell(1, 1).text = "PAN", "BNZPV4567L"

    # A tracked deletion of a name and a tracked insertion.
    d.add_paragraph()._p.append(parse_xml(
        f'<w:del {NSW} w:id="1" w:author="Meera Pillai" w:date="2026-11-01T00:00:00Z"><w:r><w:delText>Old name Ravi Kumar</w:delText></w:r></w:del>'))
    q = d.add_paragraph("Start date: ")
    q._p.append(parse_xml(f'<w:ins {NSW} w:id="2" w:author="Meera Pillai"><w:r><w:t>1 Dec 2026</w:t></w:r></w:ins>'))

    # A mailto hyperlink and a HYPERLINK field.
    h = d.add_paragraph("Email ")
    rid = d.part.relate_to("mailto:arjun.m@example.com", RT.HYPERLINK, is_external=True)
    h._p.append(parse_xml(f'<w:hyperlink {NSW} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="{rid}"><w:r><w:t>arjun.m@example.com</w:t></w:r></w:hyperlink>'))
    f = d.add_paragraph("Or ")
    for x in ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>', '<w:r><w:instrText xml:space="preserve"> HYPERLINK "mailto:hr@kestrel.example" </w:instrText></w:r>',
              '<w:r><w:fldChar w:fldCharType="separate"/></w:r>', '<w:r><w:t>write to HR</w:t></w:r>', '<w:r><w:fldChar w:fldCharType="end"/></w:r>'):
        f._p.append(parse_xml(x.replace("<w:r>", f"<w:r {NSW}>", 1)))

    # A comment by a named author, and a picture with alt text.
    c = d.add_paragraph("Please confirm by Friday.")
    d.add_comment(c.runs, text="Check with Arjun first", author="Meera Pillai", initials="MP")
    d.add_picture(png())
    d.inline_shapes[0]._inline.docPr.set("descr", "Photo of Arjun Malhotra")

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


TRICKY_DOCX_VALUES = {"Arjun Malhotra": "PERSON", "Kestrel Labs": "ORG", "₹28 lakh": "AMOUNT", "BNZPV4567L": "ID",
                      "98450 12345": "CONTACT", "arjun.m@example.com": "CONTACT", "Meera Pillai": "PERSON"}


def tricky_pptx() -> bytes:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    prs = Presentation()
    prs.core_properties.author = "Meera Pillai"
    s1 = prs.slides.add_slide(prs.slide_layouts[5])
    s1.shapes.title.text = "Acquisition of Kestrel Labs"
    box = s1.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1)).text_frame
    para = box.paragraphs[0]
    for t in ("Lead: Pri", "ya ", "Shah (priya@kestrel.example)"):
        para.add_run().text = t
    group = s1.shapes.add_group_shape()
    group.shapes.add_textbox(Inches(1), Inches(3), Inches(3), Inches(1)).text_frame.text = "Price ₹120 crore"
    rows = s1.shapes.add_table(2, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
    rows.cell(0, 0).text, rows.cell(0, 1).text = "Counsel", "Vivek Menon"
    rows.cell(1, 0).text, rows.cell(1, 1).text = "PAN", "BNZPV4567L"
    s1.notes_slide.notes_text_frame.text = "Don't tell Vivek Menon about the earn-out."
    pic = s1.shapes.add_picture(png(), Inches(7), Inches(1))
    pic._element.nvPicPr.cNvPr.set("descr", "Headshot of Priya Shah")

    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Backup: Priya Shah's compensation"
    s2._element.set("show", "0")
    data = CategoryChartData()
    data.categories = ["Priya Shah", "Vivek Menon"]
    data.add_series("Bonus", (10, 20))
    s2.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(5), Inches(3), data)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


TRICKY_PPTX_VALUES = {"Kestrel Labs": "ORG", "Priya Shah": "PERSON", "priya@kestrel.example": "CONTACT",
                      "₹120 crore": "AMOUNT", "Vivek Menon": "PERSON", "BNZPV4567L": "ID", "Meera Pillai": "PERSON"}
