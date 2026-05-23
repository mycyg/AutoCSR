"""PPTX export (M19).

Uses python-pptx to produce a concise executive-summary deck (16:9):

  * Cover slide (project + version + date)
  * Table-of-contents slide (H1 sections)
  * One slide per H1 section: title + bullet excerpts of the section body
    + an optional chart placeholder for the first associated StatBlock
  * Closing summary slide (totals + citation count)

This is intentionally "best-effort summary" — full fidelity remains the
DOCX builder's job. The intent is to give stakeholders a 5-minute
overview format from the same source content.

Output: ``data/projects/<pid>/exports/CSR_<ts>.pptx``.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.config import data_dir
from app.outline.store import load as load_outline
from app.report.store import list_drafts
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import SectionDraft

logger = logging.getLogger("autocsr.export.pptx")


@dataclass(frozen=True)
class PptxExportResult:
    path: Path
    filename: str
    size_bytes: int
    n_slides: int
    generated_at: str


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


def _h1_nodes(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []
    for n in outline.root_sections:
        out.append(n)
        # Also count direct children if there are no roots beyond a single wrapper
    return out or list(outline.root_sections)


def _summarise_section(draft: SectionDraft | None, *, max_bullets: int = 6,
                       max_bullet_chars: int = 140) -> list[str]:
    """Take the first few sentences / paragraphs / bullets of a section
    and present them as concise bullets for a slide."""
    if draft is None or not draft.markdown.strip():
        return ["(No content yet.)"]
    text = draft.markdown
    # Drop the leading H1/H2 (duplicate of slide title).
    text = re.sub(r"^\s*#{1,6}\s+[^\n]+\n+", "", text, count=1)
    bullets: list[str] = []
    # Existing markdown bullets first.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^[-*]\s+(.*)$", stripped) or re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            content = m.group(1).strip()
            if content:
                bullets.append(content[:max_bullet_chars])
        if len(bullets) >= max_bullets:
            break
    # Fallback — split paragraphs into sentences.
    if not bullets:
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        for p in paragraphs:
            sentences = re.split(r"(?<=[.!?。！？])\s+", p)
            for s in sentences:
                s_clean = s.strip()
                if len(s_clean) > 8:
                    bullets.append(s_clean[:max_bullet_chars])
                if len(bullets) >= max_bullets:
                    break
            if len(bullets) >= max_bullets:
                break
    if not bullets:
        bullets.append((text[:max_bullet_chars] + "…") if len(text) > max_bullet_chars else text)
    return bullets[:max_bullets]


# ---------------------------------------------------------------------------
# build_pptx
# ---------------------------------------------------------------------------


def build_pptx(
    project_id: str,
    *,
    progress_cb: Callable[[str], None] | None = None,
) -> PptxExportResult:
    from pptx import Presentation  # type: ignore
    from pptx.util import Cm, Pt  # type: ignore
    from pptx.dml.color import RGBColor  # type: ignore
    from pptx.enum.shapes import MSO_SHAPE  # type: ignore
    from pptx.enum.text import PP_ALIGN  # type: ignore

    outline = load_outline(project_id)
    if outline is None:
        raise RuntimeError(f"project {project_id} has no outline; build one first")

    drafts = list_drafts(project_id)
    drafts_by_id = {d.node_id: d for d in drafts}

    prs = Presentation()
    # 16:9 widescreen
    prs.slide_width = Cm(33.867)
    prs.slide_height = Cm(19.05)

    blank_layout = prs.slide_layouts[6]
    proj_name = _project_name(project_id)
    now = datetime.now()

    # Clinical-compliance workbench palette, aligned with the frontend tokens.
    navy = RGBColor(0x0B, 0x12, 0x20)
    ink = RGBColor(0x11, 0x1C, 0x2E)
    slate = RGBColor(0x47, 0x55, 0x69)
    surface = RGBColor(0xF7, 0xFA, 0xFC)
    panel = RGBColor(0xEF, 0xF6, 0xFA)
    line = RGBColor(0xD8, 0xE4, 0xEC)
    cyan = RGBColor(0x08, 0x91, 0xB2)
    blue = RGBColor(0x25, 0x63, 0xEB)
    emerald = RGBColor(0x05, 0x96, 0x69)
    amber = RGBColor(0xD9, 0x77, 0x06)
    rose = RGBColor(0xE1, 0x1D, 0x48)
    white = RGBColor(0xFF, 0xFF, 0xFF)

    font = "Microsoft YaHei"

    def _truncate(text: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _title_size(text: str, base: int = 30) -> int:
        n = len(str(text or ""))
        if n > 48:
            return max(22, base - 8)
        if n > 34:
            return max(24, base - 5)
        return base

    def _set_bg(slide, color) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = color

    def _rect(slide, *, left, top, width, height, fill, border=line,
              radius=True, weight=1.0):
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
        shp = slide.shapes.add_shape(shape_type, left, top, width, height)
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        shp.line.color.rgb = border
        shp.line.width = Pt(weight)
        return shp

    def _add_text_box(slide, *, left, top, width, height, text, size=18,
                       bold=False, color=ink, align=None, margin=0.05) -> None:
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = Cm(margin)
        tf.margin_right = Cm(margin)
        tf.margin_top = Cm(margin)
        tf.margin_bottom = Cm(margin)
        if isinstance(text, str):
            text = [text]
        for i, line in enumerate(text):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            if align is not None:
                p.alignment = align
            for run in p.runs:
                run.font.size = Pt(size)
                run.font.bold = bool(bold)
                run.font.color.rgb = color
                run.font.name = font

    def _chip(slide, *, left, top, text, fill, color=white, width=Cm(4.0)) -> None:
        _rect(slide, left=left, top=top, width=width, height=Cm(0.72),
              fill=fill, border=fill, radius=True)
        _add_text_box(slide, left=left + Cm(0.15), top=top + Cm(0.04),
                      width=width - Cm(0.3), height=Cm(0.5), text=text,
                      size=9, bold=True, color=color, align=PP_ALIGN.CENTER)

    def _bullet_card(slide, *, left, top, width, height, text, idx: int,
                     accent_color=cyan) -> None:
        _rect(slide, left=left, top=top, width=width, height=height,
              fill=white, border=line, radius=True)
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, left + Cm(0.42), top + Cm(0.45),
                                     Cm(0.34), Cm(0.34))
        dot.fill.solid()
        dot.fill.fore_color.rgb = accent_color
        dot.line.color.rgb = accent_color
        txt = _truncate(text, 150 if height > Cm(1.8) else 118)
        _add_text_box(
            slide,
            left=left + Cm(1.05),
            top=top + Cm(0.22),
            width=width - Cm(1.42),
            height=height - Cm(0.3),
            text=txt,
            size=13 if len(txt) > 105 else 14,
            color=ink,
        )

    def _add_slide_header(slide, title: str, section_id: str = "") -> None:
        _add_text_box(slide, left=Cm(1.55), top=Cm(0.8), width=Cm(23.5),
                      height=Cm(1.8), text=title, size=_title_size(title),
                      bold=True, color=ink)
        if section_id:
            _chip(slide, left=Cm(27.2), top=Cm(1.0), text=f"Section {section_id}",
                  fill=cyan, width=Cm(4.3))
        _rect(slide, left=Cm(1.55), top=Cm(2.78), width=Cm(30.8),
              height=Cm(0.04), fill=line, border=line, radius=False)

    # ---- Cover slide ------------------------------------------------------
    if progress_cb:
        progress_cb("cover")
    slide = prs.slides.add_slide(blank_layout)
    _set_bg(slide, navy)
    _rect(slide, left=Cm(0), top=Cm(0), width=Cm(1.05), height=Cm(19.05),
          fill=cyan, border=cyan, radius=False)
    _rect(slide, left=Cm(2.1), top=Cm(2.0), width=Cm(29.3), height=Cm(14.5),
          fill=RGBColor(0x10, 0x1A, 0x2D), border=RGBColor(0x1D, 0x35, 0x4A),
          radius=True)
    _chip(slide, left=Cm(3.0), top=Cm(3.0), text="CSR EXECUTIVE SUMMARY",
          fill=cyan, width=Cm(6.0))
    _add_text_box(slide, left=Cm(3.0), top=Cm(4.4), width=Cm(25.5), height=Cm(3.0),
                  text=_truncate(proj_name, 74), size=_title_size(proj_name, 40),
                  bold=True, color=white)
    _add_text_box(slide, left=Cm(3.05), top=Cm(8.2), width=Cm(22.5), height=Cm(1.3),
                  text="Clinical Study Report overview generated from current project drafts",
                  size=18, color=RGBColor(0xBA, 0xD7, 0xE8))
    for i, (label, value, color) in enumerate([
        ("Sections", str(len(list(outline.walk()))), blue),
        ("Drafts", str(sum(1 for d in drafts if d.markdown.strip())), emerald),
        ("Citations", str(sum(len(d.citations or []) for d in drafts)), amber),
    ]):
        x = Cm(3.0 + i * 6.2)
        _rect(slide, left=x, top=Cm(11.2), width=Cm(5.5), height=Cm(2.8),
              fill=RGBColor(0x13, 0x24, 0x38), border=RGBColor(0x2A, 0x48, 0x5D),
              radius=True)
        _add_text_box(slide, left=x + Cm(0.35), top=Cm(11.55), width=Cm(4.8),
                      height=Cm(0.7), text=label, size=10, bold=True,
                      color=RGBColor(0x9C, 0xB8, 0xCB))
        _add_text_box(slide, left=x + Cm(0.35), top=Cm(12.18), width=Cm(4.8),
                      height=Cm(1.1), text=value, size=26, bold=True, color=color)
    _add_text_box(slide, left=Cm(3.0), top=Cm(15.0), width=Cm(25), height=Cm(0.8),
                  text=f"Generated {now.strftime('%Y-%m-%d %H:%M')}  |  v{now.strftime('%Y%m%d-%H%M')}",
                  size=11, color=RGBColor(0x8F, 0xA8, 0xBB))

    # ---- TOC slide --------------------------------------------------------
    if progress_cb:
        progress_cb("toc")
    h1s = _h1_nodes(outline)
    slide = prs.slides.add_slide(blank_layout)
    _set_bg(slide, surface)
    _add_slide_header(slide, "Table of contents")
    cols = 2 if len(h1s) > 5 else 1
    card_w = Cm(14.7 if cols == 2 else 30.0)
    for idx, node in enumerate(h1s[:10]):
        col = idx % cols
        row = idx // cols
        left = Cm(1.7) + col * Cm(15.4)
        top = Cm(3.55) + row * Cm(2.25)
        _rect(slide, left=left, top=top, width=card_w, height=Cm(1.75),
              fill=white, border=line, radius=True)
        _chip(slide, left=left + Cm(0.35), top=top + Cm(0.42), text=node.id,
              fill=cyan if idx == 0 else blue, width=Cm(2.1))
        _add_text_box(slide, left=left + Cm(2.9), top=top + Cm(0.35),
                      width=card_w - Cm(3.25), height=Cm(1.0),
                      text=_truncate(node.title, 54 if cols == 2 else 92),
                      size=14, bold=True, color=ink)

    # ---- One slide per H1 -------------------------------------------------
    if progress_cb:
        progress_cb("sections")
    for idx, node in enumerate(h1s):
        slide = prs.slides.add_slide(blank_layout)
        _set_bg(slide, surface)
        _add_slide_header(slide, _truncate(node.title, 72), node.id)
        # Use the H1's own draft if any, else stitch a small summary from
        # the first leaf with content.
        draft = drafts_by_id.get(node.id)
        if (draft is None or not draft.markdown.strip()) and node.children:
            for child in _flatten(node):
                cd = drafts_by_id.get(child.id)
                if cd and cd.markdown.strip():
                    draft = cd
                    break
        bullets = _summarise_section(draft, max_bullets=5, max_bullet_chars=175)
        _rect(slide, left=Cm(1.55), top=Cm(3.35), width=Cm(20.7), height=Cm(13.6),
              fill=panel, border=line, radius=True)
        _add_text_box(slide, left=Cm(2.0), top=Cm(3.75), width=Cm(18.8), height=Cm(0.55),
                      text="Key takeaways", size=10, bold=True, color=cyan)
        card_h = Cm(1.78 if len(bullets) >= 5 else 2.05)
        for b_idx, bullet in enumerate(bullets[:5]):
            _bullet_card(
                slide,
                left=Cm(2.0),
                top=Cm(4.65) + b_idx * (card_h + Cm(0.36)),
                width=Cm(19.75),
                height=card_h,
                text=bullet,
                idx=b_idx,
                accent_color=cyan if b_idx == 0 else blue,
            )

        # Evidence / status rail: every section slide gets a real visual
        # anchor so the deck does not devolve into plain bullets.
        _rect(slide, left=Cm(23.0), top=Cm(3.35), width=Cm(9.3), height=Cm(13.6),
              fill=white, border=line, radius=True)
        _add_text_box(slide, left=Cm(23.55), top=Cm(3.78), width=Cm(8.0),
                      height=Cm(0.7), text="Evidence status", size=11,
                      bold=True, color=ink)
        words = int(getattr(draft, "word_count", 0) or 0) if draft else 0
        cites = len(draft.citations or []) if draft else 0
        for m_idx, (label, value, color) in enumerate([
            ("Words", f"{words:,}", blue),
            ("Citations", str(cites), emerald if cites else amber),
            ("Children", str(len(node.children)), cyan),
        ]):
            y = Cm(5.0 + m_idx * 2.05)
            _rect(slide, left=Cm(23.55), top=y, width=Cm(8.2), height=Cm(1.55),
                  fill=RGBColor(0xF8, 0xFB, 0xFD), border=line, radius=True)
            _add_text_box(slide, left=Cm(23.95), top=y + Cm(0.18), width=Cm(3.2),
                          height=Cm(0.5), text=label, size=9, bold=True,
                          color=slate)
            _add_text_box(slide, left=Cm(29.0), top=y + Cm(0.12), width=Cm(2.4),
                          height=Cm(0.7), text=value, size=18, bold=True,
                          color=color, align=PP_ALIGN.RIGHT)
        refs = []
        if draft:
            refs = [_truncate(c.ref_code or c.locator or c.type, 32) for c in (draft.citations or [])[:3]]
        ref_lines = refs or ["No linked evidence yet"]
        _add_text_box(slide, left=Cm(23.55), top=Cm(11.7), width=Cm(8.2), height=Cm(0.45),
                      text="Linked refs", size=9, bold=True, color=slate)
        _add_text_box(slide, left=Cm(23.55), top=Cm(12.35), width=Cm(8.2), height=Cm(2.4),
                      text=ref_lines, size=9, color=slate)
        # Footer
        _add_text_box(slide, left=Cm(28.2), top=Cm(17.55), width=Cm(4), height=Cm(0.5),
                      text=f"{idx + 1} / {len(h1s)}", size=9, color=slate,
                      align=PP_ALIGN.RIGHT)
        if progress_cb and idx % 5 == 0:
            progress_cb(f"slide:{idx + 1}/{len(h1s)}")

    # ---- Summary slide ----------------------------------------------------
    if progress_cb:
        progress_cb("summary")
    n_drafts = sum(1 for d in drafts if d.markdown.strip())
    total_words = sum(int(getattr(d, "word_count", 0) or 0) for d in drafts)
    cites = sum(len(d.citations or []) for d in drafts)
    slide = prs.slides.add_slide(blank_layout)
    _set_bg(slide, navy)
    _rect(slide, left=Cm(0), top=Cm(0), width=Cm(33.867), height=Cm(1.0),
          fill=cyan, border=cyan, radius=False)
    _add_text_box(slide, left=Cm(2.0), top=Cm(2.4), width=Cm(24.0), height=Cm(1.2),
                  text="Export summary", size=34, bold=True, color=white)
    _add_text_box(slide, left=Cm(2.0), top=Cm(3.75), width=Cm(24.0), height=Cm(0.9),
                  text=_truncate(proj_name, 88), size=15,
                  color=RGBColor(0xBA, 0xD7, 0xE8))
    for i, (label, value, color) in enumerate([
        ("Sections drafted", f"{n_drafts} / {len(list(outline.walk()))}", blue),
        ("Total words", f"{total_words:,}", emerald),
        ("Citations", str(cites), amber if cites else rose),
    ]):
        x = Cm(2.0 + i * 10.3)
        _rect(slide, left=x, top=Cm(6.1), width=Cm(9.2), height=Cm(5.4),
              fill=RGBColor(0x10, 0x1A, 0x2D), border=RGBColor(0x2A, 0x48, 0x5D),
              radius=True)
        _add_text_box(slide, left=x + Cm(0.55), top=Cm(6.7), width=Cm(7.9),
                      height=Cm(0.7), text=label, size=11, bold=True,
                      color=RGBColor(0x9C, 0xB8, 0xCB))
        _add_text_box(slide, left=x + Cm(0.55), top=Cm(8.0), width=Cm(7.9),
                      height=Cm(1.6), text=value, size=30, bold=True, color=color)
    _add_text_box(slide, left=Cm(2.0), top=Cm(14.4), width=Cm(28.5), height=Cm(1.0),
                  text=f"Generated {now.strftime('%Y-%m-%d %H:%M')} from current AutoCSR draft state.",
                  size=13, color=RGBColor(0xBA, 0xD7, 0xE8))

    # ---- Save -------------------------------------------------------------
    out_path = _exports_dir(project_id) / f"CSR_{now.strftime('%Y%m%d_%H%M%S')}.pptx"
    prs.save(str(out_path))
    size = out_path.stat().st_size

    if progress_cb:
        progress_cb("done")

    n_slides = len(prs.slides)
    return PptxExportResult(
        path=out_path,
        filename=out_path.name,
        size_bytes=size,
        n_slides=n_slides,
        generated_at=now.isoformat(timespec="seconds"),
    )


def _flatten(node: OutlineNode) -> list[OutlineNode]:
    out = []
    for c in node.children:
        out.append(c)
        out.extend(_flatten(c))
    return out


__all__ = ["build_pptx", "PptxExportResult"]
