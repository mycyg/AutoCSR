"""Programmatic ICH E3 docx template.

We do **not** ship a binary .docx in git; the template is built on-the-fly with
python-docx defaults plus targeted style overrides (heading fonts, table grid,
header/footer placeholders). The docx_builder then opens a fresh template,
fills placeholders, and appends body content.

Placeholders used downstream:
    {{PROJECT_NAME}}        — set by builder
    {{REPORT_TITLE}}        — set by builder
    {{VERSION}}             — set by builder
    {{GENERATED_DATE}}      — set by builder (yyyy-mm-dd HH:MM)
    {{COMPLIANCE_NOTE}}     — set by builder (cleansing pipeline summary)
"""
from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm


HEADING_FONTS = {
    1: ("微软雅黑", Pt(20), True),
    2: ("微软雅黑", Pt(16), True),
    3: ("微软雅黑", Pt(13), True),
    4: ("微软雅黑", Pt(12), True),
}


def _set_heading_styles(doc: Document) -> None:
    for level, (font, size, bold) in HEADING_FONTS.items():
        try:
            style = doc.styles[f"Heading {level}"]
        except KeyError:
            continue
        r = style.font
        r.name = font
        r.size = size
        r.bold = bold
        # Eastern Asian font hint for CJK
        rPr = style.element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:eastAsia"), font)


def _set_normal_style(doc: Document) -> None:
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(11)
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), "宋体")


def _add_field(paragraph, instr: str) -> None:
    """Insert a Word field (e.g. TOC, PAGE) into ``paragraph``."""
    run = paragraph.add_run()
    fldChar_begin = OxmlElement("w:fldChar")
    fldChar_begin.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = instr
    fldChar_sep = OxmlElement("w:fldChar")
    fldChar_sep.set(qn("w:fldCharType"), "separate")
    fldChar_end = OxmlElement("w:fldChar")
    fldChar_end.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar_begin)
    run._r.append(instrText)
    run._r.append(fldChar_sep)
    run._r.append(fldChar_end)


def _add_page_number_run(paragraph) -> None:
    _add_field(paragraph, "PAGE")
    paragraph.add_run(" / ")
    _add_field(paragraph, "NUMPAGES")


def _add_header_footer(doc: Document) -> None:
    section = doc.sections[0]
    # different first page so cover stays clean
    section.different_first_page_header_footer = True
    header = section.header
    h_para = header.paragraphs[0]
    h_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    h_run = h_para.add_run("{{PROJECT_NAME}} · CSR")
    h_run.font.size = Pt(9)

    footer = section.footer
    f_para = footer.paragraphs[0]
    f_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    f_run = f_para.add_run("机密 · 第 ")
    f_run.font.size = Pt(9)
    _add_page_number_run(f_para)
    tail = f_para.add_run(" 页")
    tail.font.size = Pt(9)


def _add_cover(doc: Document) -> None:
    # ---- Big spacer + title ---------------------------------------------------
    for _ in range(4):
        doc.add_paragraph()
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run("{{REPORT_TITLE}}")
    title_run.bold = True
    title_run.font.size = Pt(28)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = sub_p.add_run("Clinical Study Report (ICH E3)")
    sub_run.font.size = Pt(14)
    sub_run.italic = True

    for _ in range(4):
        doc.add_paragraph()

    info = doc.add_paragraph()
    info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    info.add_run("项目: ").bold = True
    info.add_run("{{PROJECT_NAME}}")

    ver = doc.add_paragraph()
    ver.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ver.add_run("版本: ").bold = True
    ver.add_run("{{VERSION}}")

    dt = doc.add_paragraph()
    dt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    dt.add_run("生成日期: ").bold = True
    dt.add_run("{{GENERATED_DATE}}")

    for _ in range(3):
        doc.add_paragraph()

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note_run = note.add_run("{{COMPLIANCE_NOTE}}")
    note_run.italic = True
    note_run.font.size = Pt(10)

    # Force new section so the TOC starts on a fresh page
    doc.add_section(WD_SECTION.NEW_PAGE)


def _add_toc(doc: Document) -> None:
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = p_title.add_run("目  录")
    tr.bold = True
    tr.font.size = Pt(16)
    doc.add_paragraph()

    p = doc.add_paragraph()
    _add_field(p, r'TOC \o "1-3" \h \z \u')

    note = doc.add_paragraph()
    note_run = note.add_run("（在 Word 中按 F9 刷新目录）")
    note_run.italic = True
    note_run.font.size = Pt(9)

    doc.add_section(WD_SECTION.NEW_PAGE)


def create_template() -> Document:
    """Build a fresh ICH E3 template Document."""
    doc = Document()
    _set_normal_style(doc)
    _set_heading_styles(doc)

    # 1.5cm margins on A4
    for section in doc.sections:
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)

    _add_header_footer(doc)
    _add_cover(doc)
    _add_toc(doc)
    return doc


__all__ = ["create_template"]
