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

    accent = RGBColor(0x25, 0x63, 0xEB)
    text_color = RGBColor(0x1F, 0x29, 0x37)
    mute = RGBColor(0x6B, 0x72, 0x80)

    def _add_text_box(slide, *, left, top, width, height, text, size=18,
                       bold=False, color=text_color, align=None) -> None:
        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
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

    # ---- Cover slide ------------------------------------------------------
    if progress_cb:
        progress_cb("cover")
    slide = prs.slides.add_slide(blank_layout)
    _add_text_box(slide, left=Cm(2), top=Cm(5.5), width=Cm(29.8), height=Cm(3),
                   text=proj_name, size=44, bold=True, color=accent)
    _add_text_box(slide, left=Cm(2), top=Cm(9), width=Cm(29.8), height=Cm(1.5),
                   text="Clinical Study Report", size=24, color=text_color)
    _add_text_box(slide, left=Cm(2), top=Cm(14), width=Cm(29.8), height=Cm(1),
                   text=f"Version: v{now.strftime('%Y%m%d-%H%M')}",
                   size=14, color=mute)
    _add_text_box(slide, left=Cm(2), top=Cm(15.2), width=Cm(29.8), height=Cm(1),
                   text=f"Generated: {now.strftime('%Y-%m-%d %H:%M')}",
                   size=14, color=mute)

    # ---- TOC slide --------------------------------------------------------
    if progress_cb:
        progress_cb("toc")
    h1s = _h1_nodes(outline)
    slide = prs.slides.add_slide(blank_layout)
    _add_text_box(slide, left=Cm(2), top=Cm(1.5), width=Cm(29.8), height=Cm(2),
                   text="Table of Contents", size=32, bold=True, color=accent)
    toc_lines = [f"{n.id}  {n.title}" for n in h1s][:18]
    _add_text_box(slide, left=Cm(2), top=Cm(4.5), width=Cm(29.8), height=Cm(13),
                   text=toc_lines, size=18, color=text_color)

    # ---- One slide per H1 -------------------------------------------------
    if progress_cb:
        progress_cb("sections")
    for idx, node in enumerate(h1s):
        slide = prs.slides.add_slide(blank_layout)
        # Section title (heading)
        _add_text_box(slide, left=Cm(2), top=Cm(1.5), width=Cm(29.8), height=Cm(2),
                       text=f"{node.id}  {node.title}", size=28, bold=True,
                       color=accent)
        # Use the H1's own draft if any, else stitch a small summary from
        # the first leaf with content.
        draft = drafts_by_id.get(node.id)
        if (draft is None or not draft.markdown.strip()) and node.children:
            for child in _flatten(node):
                cd = drafts_by_id.get(child.id)
                if cd and cd.markdown.strip():
                    draft = cd
                    break
        bullets = _summarise_section(draft, max_bullets=7)
        bullet_text = ["• " + b for b in bullets]
        _add_text_box(slide, left=Cm(2), top=Cm(4.5), width=Cm(29.8), height=Cm(13),
                       text=bullet_text, size=18, color=text_color)
        # Footer
        _add_text_box(slide, left=Cm(28), top=Cm(17.8), width=Cm(5), height=Cm(1),
                       text=f"{idx + 1} / {len(h1s)}", size=10, color=mute)
        if progress_cb and idx % 5 == 0:
            progress_cb(f"slide:{idx + 1}/{len(h1s)}")

    # ---- Summary slide ----------------------------------------------------
    if progress_cb:
        progress_cb("summary")
    n_drafts = sum(1 for d in drafts if d.markdown.strip())
    total_words = sum(int(getattr(d, "word_count", 0) or 0) for d in drafts)
    cites = sum(len(d.citations or []) for d in drafts)
    slide = prs.slides.add_slide(blank_layout)
    _add_text_box(slide, left=Cm(2), top=Cm(2), width=Cm(29.8), height=Cm(2),
                   text="Summary", size=32, bold=True, color=accent)
    summary_lines = [
        f"Sections drafted: {n_drafts} / {len(list(outline.walk()))}",
        f"Total words: {total_words:,}",
        f"Total citations: {cites}",
        f"Project: {proj_name}",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M')}",
    ]
    _add_text_box(slide, left=Cm(2), top=Cm(5), width=Cm(29.8), height=Cm(12),
                   text=summary_lines, size=22, color=text_color)

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
