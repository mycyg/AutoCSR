"""PDF export (M19).

Uses ``reportlab`` to render the same content the DOCX builder produces,
but as a self-contained PDF. We re-use ``DocxTemplateConfig`` so users
who already configured fonts / margins / header / footer for the .docx
export get the same look without having to re-configure.

Pipeline mirrors :mod:`app.export.docx_builder`:

  1. Cover (title + version + generated_date + compliance note)
  2. Auto-generated table of contents
  3. For each outline node in print order:
       - Heading at the right level (1..4)
       - Section markdown rendered to PDF flowables
       - Markdown tables → ``reportlab.platypus.Table`` with grid style
  4. References chapter (one paragraph per unique citation)
  5. Appendix A — cleansing pipeline rule summary
  6. Appendix B — StatBlock index

Output: ``data/projects/<pid>/exports/CSR_<ts>.pdf``.

Best-effort layout: complex markdown (deep blockquotes, code blocks with
syntax) is flattened to plain paragraphs. The DOCX builder remains the
primary export channel; PDF is positioned as "fast preview / final".
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.analysis import store as analysis_store
from app.cleansing import pipeline_io as cleansing_pipeline
from app.config import data_dir
from app.export.template_engine import (
    DocxTemplateConfig, load_config as load_template_config,
)
from app.outline.store import load as load_outline
from app.report.store import list_drafts
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import SectionDraft

logger = logging.getLogger("autocsr.export.pdf")


@dataclass(frozen=True)
class PdfExportResult:
    path: Path
    filename: str
    size_bytes: int
    n_sections: int
    n_citations: int
    generated_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_name(project_id: str) -> str:
    proj_file = data_dir() / "projects.json"
    if proj_file.exists():
        try:
            items = json.loads(proj_file.read_text(encoding="utf-8") or "[]")
            for it in items:
                if it.get("id") == project_id:
                    return str(it.get("name") or project_id)
        except Exception:
            pass
    return project_id


def _exports_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _walk_in_order(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []

    def _w(n: OutlineNode) -> None:
        out.append(n)
        for c in n.children:
            _w(c)

    for root in outline.root_sections:
        _w(root)
    return out


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0.0, 0.0, 0.0)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return (0.0, 0.0, 0.0)


_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def _parse_markdown_blocks(markdown_text: str) -> list[dict]:
    """Very small markdown → block parser tailored to the section
    markdown produced by writer_agent. We recognise: H1..H6, paragraphs,
    bullet/numbered lists, and pipe tables.
    """
    out: list[dict] = []
    lines = (markdown_text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # Heading
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            out.append({"type": "h", "level": len(m.group(1)),
                        "text": m.group(2).strip()})
            i += 1
            continue
        # Table — consume contiguous lines that start with "|"
        if _TABLE_LINE.match(stripped):
            table_lines: list[str] = []
            while i < len(lines) and _TABLE_LINE.match(lines[i].strip() or ""):
                table_lines.append(lines[i].strip())
                i += 1
            rows = []
            for tl in table_lines:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                # Skip the alignment row ("---")
                if all(re.fullmatch(r":?-+:?", c or "") for c in cells):
                    continue
                rows.append(cells)
            if rows:
                out.append({"type": "table", "rows": rows})
            continue
        # Unordered list
        if re.match(r"^\s*[-*]\s+", line):
            items: list[str] = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]).strip())
                i += 1
            out.append({"type": "ul", "items": items})
            continue
        # Ordered list
        if re.match(r"^\s*\d+[.)]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+[.)]\s+", "", lines[i]).strip())
                i += 1
            out.append({"type": "ol", "items": items})
            continue
        # Paragraph — consume until blank line
        para: list[str] = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip():
            para.append(lines[i].strip())
            i += 1
        out.append({"type": "p", "text": " ".join(para)})
    return out


def _md_inline_to_html(text: str) -> str:
    """Reportlab Paragraph parses a small subset of HTML. We translate
    **bold**, *italic*, `code` and escape stray < > & ."""
    # Escape HTML first.
    safe = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
    safe = re.sub(r"\*(.+?)\*", r"<i>\1</i>", safe)
    safe = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", safe)
    return safe


def _gather_cleansing_summary(project_id: str) -> tuple[list[list[str]], int]:
    try:
        yaml_text = cleansing_pipeline.export_pipeline(project_id) or ""
    except Exception:
        yaml_text = ""
    rule_count = 0
    by_type: dict[str, int] = {}
    try:
        import yaml as _yaml
        data = _yaml.safe_load(yaml_text) or {}
        rules = data.get("rules") or data.get("proposals") or []
        if isinstance(rules, list):
            rule_count = len(rules)
            for r in rules:
                t = str(r.get("type") or r.get("op") or "unknown")
                by_type[t] = by_type.get(t, 0) + 1
    except Exception:
        pass
    rows = [["Type", "Count"]]
    if by_type:
        for k, v in sorted(by_type.items()):
            rows.append([k, str(v)])
    else:
        rows.append(["(none)", "0"])
    return rows, rule_count


def _gather_analysis_table(project_id: str) -> list[list[str]]:
    try:
        idx = analysis_store.list_blocks(project_id)
    except Exception:
        idx = []
    rows = [["ID", "Type", "Title", "Source"]]
    for s in idx:
        rows.append([
            str(s.get("id") or "")[:12],
            str(s.get("analysis_type") or ""),
            str(s.get("title") or "")[:60],
            ", ".join(s.get("source_files") or [])[:60],
        ])
    if len(rows) == 1:
        rows.append(["(none)", "", "", ""])
    return rows


def _gather_unique_citations(drafts: list[SectionDraft]) -> list[dict]:
    seen: dict[str, dict] = {}
    for d in drafts:
        for c in d.citations or []:
            if c.ref_code in seen:
                continue
            seen[c.ref_code] = {
                "ref_code": c.ref_code,
                "type": c.type,
                "snippet": (c.snippet or "")[:200],
            }
    return list(seen.values())


# ---------------------------------------------------------------------------
# build_pdf
# ---------------------------------------------------------------------------


def build_pdf(
    project_id: str,
    *,
    template_config: DocxTemplateConfig | dict | None = None,
    include_compliance_note: bool = True,
    include_appendix_cleansing: bool = True,
    include_appendix_analysis: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> PdfExportResult:
    # Lazy import — keeps module load cheap when reportlab is absent.
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore
    from reportlab.lib.units import cm  # type: ignore
    from reportlab.platypus import (  # type: ignore
        BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer,
        Table, TableStyle,
    )

    outline = load_outline(project_id)
    if outline is None:
        raise RuntimeError(f"project {project_id} has no outline; build one first")
    drafts = list_drafts(project_id)
    drafts_by_id = {d.node_id: d for d in drafts}

    # Resolve template config.
    cfg: DocxTemplateConfig
    if isinstance(template_config, DocxTemplateConfig):
        cfg = template_config
    elif isinstance(template_config, dict):
        try:
            cfg = DocxTemplateConfig(**template_config)
        except Exception:
            cfg = load_template_config(project_id)
    else:
        cfg = load_template_config(project_id)

    proj_name = _project_name(project_id)
    now = datetime.now()
    out_path = _exports_dir(project_id) / f"CSR_{now.strftime('%Y%m%d_%H%M%S')}.pdf"

    # ---- Document scaffolding ---------------------------------------------
    if progress_cb:
        progress_cb("init")

    margins = (
        cfg.margins.left * cm,
        cfg.margins.right * cm,
        cfg.margins.top * cm,
        cfg.margins.bottom * cm,
    )
    doc = BaseDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=margins[0],
        rightMargin=margins[1],
        topMargin=margins[2],
        bottomMargin=margins[3],
        title=f"{proj_name} CSR",
        author="AutoCSR",
    )

    # Header / footer + optional watermark.
    header_text = cfg.header_text or ""
    footer_text = cfg.footer_text or ""
    watermark = cfg.watermark or ""

    def _draw_chrome(canvas, _doc) -> None:  # noqa: ANN001
        canvas.saveState()
        try:
            if header_text:
                canvas.setFont("Helvetica", 8)
                canvas.setFillGray(0.4)
                canvas.drawString(margins[0], A4[1] - margins[2] / 2,
                                  header_text[:200])
            if footer_text or True:
                canvas.setFont("Helvetica", 8)
                canvas.setFillGray(0.4)
                page_no = f"Page {_doc.page}"
                ft = (footer_text + "  ·  " + page_no) if footer_text else page_no
                canvas.drawString(margins[0], margins[3] / 2, ft[:200])
            if watermark:
                canvas.saveState()
                canvas.setFont("Helvetica-Bold", 60)
                canvas.setFillGray(0.85)
                canvas.translate(A4[0] / 2, A4[1] / 2)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, watermark[:60])
                canvas.restoreState()
        finally:
            canvas.restoreState()

    frame = Frame(
        margins[0], margins[3],
        A4[0] - margins[0] - margins[1],
        A4[1] - margins[2] - margins[3],
        id="body",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_draw_chrome)])

    # ---- Styles -----------------------------------------------------------
    styles = getSampleStyleSheet()
    body_size = cfg.sizes.body
    h_color = colors.Color(*_hex_to_rgb(cfg.colors.heading))
    body_color = colors.Color(*_hex_to_rgb(cfg.colors.body))

    # Reportlab's default fonts are Helvetica/Times — keep it that way for
    # widest compatibility. CJK fonts require a registered TTF which we
    # cannot guarantee inside slim Docker images; we still flatten CJK to
    # the default sans, which prints visibly.
    body_style = ParagraphStyle(
        "body", parent=styles["BodyText"],
        fontName="Helvetica", fontSize=body_size,
        leading=body_size * cfg.line_spacing,
        textColor=body_color,
        spaceAfter=4,
    )

    def _h_style(level: int) -> ParagraphStyle:
        size_map = {1: cfg.sizes.h1, 2: cfg.sizes.h2, 3: cfg.sizes.h3, 4: max(cfg.sizes.h3 - 1, 10)}
        sz = size_map.get(level, cfg.sizes.body)
        return ParagraphStyle(
            f"H{level}", parent=styles["Heading1"],
            fontName="Helvetica-Bold", fontSize=sz,
            leading=sz * 1.2, textColor=h_color,
            spaceBefore=max(8, sz / 2), spaceAfter=4,
        )

    cover_title_style = ParagraphStyle(
        "cover_title", parent=styles["Title"],
        fontSize=24, leading=30, alignment=1, spaceAfter=24,
        textColor=h_color,
    )
    cover_sub_style = ParagraphStyle(
        "cover_sub", parent=styles["BodyText"],
        fontSize=12, leading=16, alignment=1, spaceAfter=12,
    )

    story: list = []

    # ---- Cover ------------------------------------------------------------
    if progress_cb:
        progress_cb("cover")
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph(f"{proj_name}", cover_title_style))
    story.append(Paragraph("Clinical Study Report", cover_sub_style))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(f"Version: v{now.strftime('%Y%m%d-%H%M')}", cover_sub_style))
    story.append(Paragraph(f"Generated: {now.strftime('%Y-%m-%d %H:%M')}", cover_sub_style))
    if include_compliance_note:
        rows, rule_count = _gather_cleansing_summary(project_id)
        story.append(Spacer(1, 1 * cm))
        story.append(Paragraph(
            f"<i>Compliance: data cleansed via pipeline v1 with {rule_count} rules.</i>",
            cover_sub_style,
        ))
    else:
        _rows, rule_count = _gather_cleansing_summary(project_id)
    story.append(PageBreak())

    # ---- Table of contents (flat) ----------------------------------------
    if progress_cb:
        progress_cb("toc")
    story.append(Paragraph("Table of Contents", _h_style(1)))
    nodes = _walk_in_order(outline)
    toc_style = ParagraphStyle(
        "toc", parent=body_style, leftIndent=12, spaceAfter=2,
    )
    for n in nodes:
        indent = max(0, (int(getattr(n, "level", 1) or 1) - 1) * 12)
        toc_style_local = ParagraphStyle(
            f"toc_{indent}", parent=toc_style, leftIndent=indent,
        )
        story.append(Paragraph(f"{n.id}  {n.title}", toc_style_local))
    story.append(PageBreak())

    # ---- Body sections ----------------------------------------------------
    if progress_cb:
        progress_cb("sections")
    for idx, node in enumerate(nodes):
        lvl = max(1, min(int(getattr(node, "level", 1) or 1), 4))
        story.append(Paragraph(f"{node.id}  {node.title}", _h_style(lvl)))
        draft = drafts_by_id.get(node.id)
        if draft and draft.markdown.strip():
            md = re.sub(r"^##\s+[^\n]+\n+", "", draft.markdown.strip(), count=1)
            for blk in _parse_markdown_blocks(md):
                if blk["type"] == "h":
                    story.append(Paragraph(
                        _md_inline_to_html(blk["text"]),
                        _h_style(min(lvl + 1, 4))),
                    )
                elif blk["type"] == "p":
                    story.append(Paragraph(_md_inline_to_html(blk["text"]), body_style))
                elif blk["type"] == "ul":
                    for it in blk["items"]:
                        story.append(Paragraph(
                            "&bull;&nbsp;&nbsp;" + _md_inline_to_html(it),
                            body_style,
                        ))
                elif blk["type"] == "ol":
                    for k, it in enumerate(blk["items"], 1):
                        story.append(Paragraph(
                            f"{k}.&nbsp;&nbsp;" + _md_inline_to_html(it),
                            body_style,
                        ))
                elif blk["type"] == "table":
                    rows = blk["rows"]
                    if not rows:
                        continue
                    t = Table(rows, hAlign="LEFT")
                    t.setStyle(TableStyle([
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), max(body_size - 1, 7)),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 6))
        elif not node.children:
            story.append(Paragraph("<i>(This section is empty.)</i>", body_style))
        if progress_cb and idx % 5 == 0:
            progress_cb(f"section:{idx + 1}/{len(nodes)}")

    # ---- References -------------------------------------------------------
    if progress_cb:
        progress_cb("references")
    story.append(PageBreak())
    story.append(Paragraph("References", _h_style(1)))
    cites = _gather_unique_citations(drafts)
    if cites:
        for c in cites:
            story.append(Paragraph(
                f"<b>[{c['ref_code']}]</b> ({c['type']}) {_md_inline_to_html(c['snippet'])}",
                body_style,
            ))
    else:
        story.append(Paragraph("<i>(No resolved citations.)</i>", body_style))

    # ---- Appendix A: cleansing -------------------------------------------
    if include_appendix_cleansing:
        if progress_cb:
            progress_cb("appendix_a")
        story.append(PageBreak())
        story.append(Paragraph("Appendix A — Cleansing Pipeline Summary",
                                _h_style(1)))
        rows, rule_count = _gather_cleansing_summary(project_id)
        t = Table(rows, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(t)

    # ---- Appendix B: analysis --------------------------------------------
    if include_appendix_analysis:
        if progress_cb:
            progress_cb("appendix_b")
        story.append(PageBreak())
        story.append(Paragraph("Appendix B — Analysis Methods Summary",
                                _h_style(1)))
        rows = _gather_analysis_table(project_id)
        t = Table(rows, hAlign="LEFT", colWidths=[3 * cm, 3 * cm, 7 * cm, 4 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)

    if progress_cb:
        progress_cb("rendering")

    doc.build(story)
    size = out_path.stat().st_size

    if progress_cb:
        progress_cb("done")

    return PdfExportResult(
        path=out_path,
        filename=out_path.name,
        size_bytes=size,
        n_sections=len(nodes),
        n_citations=len(cites),
        generated_at=now.isoformat(timespec="seconds"),
    )


__all__ = ["build_pdf", "PdfExportResult"]
