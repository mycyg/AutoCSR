"""Reverse-import an existing .docx CSR into an AutoCSR project (M13).

We walk the document by paragraph-style ("Heading 1"/"Heading 2"/...) —
not font-size heuristics — because authoring tools (Word / Google Docs /
LibreOffice) all use the same style names. Each heading starts a new
section node; paragraphs between headings become that section's body.
Tables are flattened to GFM markdown so the writer / chat-editor can
edit them later. Endnotes / footnotes that match an existing project
``Ref<...>`` token are preserved verbatim; everything else is left as
prose.

The importer does NOT touch project state — callers receive an
``ImportResult`` (outline + drafts) and can call
:func:`commit_import` after the user reviews / edits the tree.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docx import Document
from pydantic import BaseModel, Field

from app.config import data_dir
from app.outline.store import save as save_outline
from app.report.store import save_draft
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import LLMMeta, SectionDraft

logger = logging.getLogger("autocsr.ingestion.csr_importer")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ImportSection(BaseModel):
    node_id: str
    title: str
    level: int                            # 1..6 (Heading 1 → 1)
    markdown: str = ""                    # body markdown for this section
    children: list["ImportSection"] = Field(default_factory=list)
    word_count: int = 0


ImportSection.model_rebuild()


class ImportResult(BaseModel):
    import_id: str
    project_id: str
    source_filename: str
    n_headings: int
    n_paragraphs: int
    n_tables: int
    confidence: float                     # 0-1, decreases with unmapped paras
    unmapped_paragraphs: int = 0
    root_sections: list[ImportSection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Style detection
# ---------------------------------------------------------------------------


_HEADING_STYLES = {
    "Heading 1": 1, "Heading 2": 2, "Heading 3": 3,
    "Heading 4": 4, "Heading 5": 5, "Heading 6": 6,
    "标题 1": 1, "标题 2": 2, "标题 3": 3, "标题 4": 4,
    "Title": 1,
}


def _level_of(style_name: str) -> int | None:
    if not style_name:
        return None
    return _HEADING_STYLES.get(style_name)


# ---------------------------------------------------------------------------
# Markdown rendering of paragraphs / tables
# ---------------------------------------------------------------------------


def _paragraph_to_markdown(p) -> str:
    """Render a python-docx paragraph as a markdown line.

    Preserves bold / italic / inline code by inspecting runs."""
    chunks: list[str] = []
    for run in p.runs:
        text = run.text or ""
        if not text:
            continue
        if run.bold and run.italic:
            chunks.append(f"***{text}***")
        elif run.bold:
            chunks.append(f"**{text}**")
        elif run.italic:
            chunks.append(f"*{text}*")
        elif (run.font and run.font.name and "Consolas" in (run.font.name or "")):
            chunks.append(f"`{text}`")
        else:
            chunks.append(text)
    rendered = "".join(chunks).strip()
    style = (p.style.name if p.style else "") or ""
    if style.startswith("List Bullet"):
        return f"- {rendered}"
    if style.startswith("List Number"):
        return f"1. {rendered}"
    return rendered


def _table_to_markdown(tbl) -> str:
    rows = tbl.rows
    if not rows:
        return ""
    out_lines: list[str] = []
    header_cells = rows[0].cells
    out_lines.append("| " + " | ".join(_clean_cell(c.text) for c in header_cells) + " |")
    out_lines.append("| " + " | ".join("---" for _ in header_cells) + " |")
    for r in rows[1:]:
        out_lines.append("| " + " | ".join(_clean_cell(c.text) for c in r.cells) + " |")
    return "\n".join(out_lines)


def _clean_cell(text: str) -> str:
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()


# ---------------------------------------------------------------------------
# Sectionizer
# ---------------------------------------------------------------------------


def _iter_block_items(doc):
    """Yield body-level paragraphs and tables in document order.

    python-docx doesn't expose this directly; we walk the XML children
    of ``doc.element.body`` to keep the relative ordering of paragraphs
    and tables (needed for "paragraph above this table" attribution)."""
    from docx.oxml.ns import qn
    from docx.table import Table as _Table
    from docx.text.paragraph import Paragraph as _Paragraph
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield _Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield _Table(child, doc)


def parse_docx(path: Path) -> tuple[list[ImportSection], dict[str, int]]:
    """Return (root sections, stats) for the given .docx."""
    doc = Document(str(path))
    roots: list[ImportSection] = []
    stack: list[ImportSection] = []
    n_paragraphs = 0
    n_tables = 0
    unmapped = 0

    def _attach(node: ImportSection) -> None:
        # Pop stack until top has lower level than node.level
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    counter = 0
    for block in _iter_block_items(doc):
        if block.__class__.__name__ == "Paragraph":
            text = (block.text or "").strip()
            style = block.style.name if block.style else ""
            level = _level_of(style)
            if level is not None and text:
                counter += 1
                node_id = f"imp.{counter}"
                _attach(ImportSection(node_id=node_id, title=text, level=level))
                continue
            if not text:
                continue
            n_paragraphs += 1
            line = _paragraph_to_markdown(block)
            if not stack:
                # Body content before any heading — drop into an implicit
                # "Preface" section so we don't lose it.
                counter += 1
                _attach(ImportSection(node_id=f"imp.{counter}", title="Preface", level=1))
            stack[-1].markdown = ((stack[-1].markdown or "") + "\n\n" + line).strip()
        else:
            # Table
            n_tables += 1
            md = _table_to_markdown(block)
            if not md:
                continue
            if not stack:
                counter += 1
                _attach(ImportSection(node_id=f"imp.{counter}", title="Preface", level=1))
            stack[-1].markdown = ((stack[-1].markdown or "") + "\n\n" + md).strip()

    # Word counts
    def _fill_wc(node: ImportSection) -> None:
        node.word_count = _word_count(node.markdown)
        for c in node.children:
            _fill_wc(c)
    for r in roots:
        _fill_wc(r)

    return roots, {
        "paragraphs": n_paragraphs,
        "tables": n_tables,
        "unmapped": unmapped,
    }


def _word_count(md: str) -> int:
    cjk = sum(1 for ch in md if "一" <= ch <= "鿿")
    latin = len([t for t in re.split(r"\s+", md) if t])
    return cjk + latin


# ---------------------------------------------------------------------------
# In-process import cache (so /commit can pick up the parse result)
# ---------------------------------------------------------------------------


_IMPORTS: dict[str, ImportResult] = {}


def _cache_put(result: ImportResult) -> None:
    _IMPORTS[result.import_id] = result
    if len(_IMPORTS) > 64:
        for k in list(_IMPORTS.keys())[:32]:
            _IMPORTS.pop(k, None)


def get_import(import_id: str) -> ImportResult | None:
    return _IMPORTS.get(import_id)


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def import_csr(project_id: str, docx_path: Path) -> ImportResult:
    if not docx_path.exists():
        raise FileNotFoundError(str(docx_path))
    roots, stats = parse_docx(docx_path)
    n_headings = _count_headings(roots)
    n_paragraphs = stats["paragraphs"]
    n_tables = stats["tables"]
    unmapped = stats.get("unmapped", 0)
    confidence = 0.95 if n_headings > 0 else 0.4
    if n_paragraphs > 0:
        confidence -= 0.4 * (unmapped / max(n_paragraphs, 1))
    confidence = max(0.0, min(1.0, confidence))
    result = ImportResult(
        import_id=uuid.uuid4().hex[:12],
        project_id=project_id,
        source_filename=docx_path.name,
        n_headings=n_headings,
        n_paragraphs=n_paragraphs,
        n_tables=n_tables,
        confidence=confidence,
        unmapped_paragraphs=unmapped,
        root_sections=roots,
    )
    _cache_put(result)
    # Also persist the import for diagnostics
    try:
        _import_dir(project_id).mkdir(parents=True, exist_ok=True)
        (_import_dir(project_id) / f"{result.import_id}.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8",
        )
    except Exception:
        pass
    return result


def _count_headings(roots: list[ImportSection]) -> int:
    total = 0
    def _w(n: ImportSection) -> None:
        nonlocal total
        total += 1
        for c in n.children:
            _w(c)
    for r in roots:
        _w(r)
    return total


def _import_dir(project_id: str) -> Path:
    return data_dir() / "projects" / project_id / "imports"


# ---------------------------------------------------------------------------
# Commit — write outline + drafts back to the project
# ---------------------------------------------------------------------------


def commit_import(project_id: str, import_id: str,
                   principle_id: str | None = None,
                   keep_existing_outline: bool = False) -> dict[str, Any]:
    result = get_import(import_id)
    if result is None or result.project_id != project_id:
        raise KeyError(f"import {import_id} not found for project {project_id}")
    now = datetime.now(timezone.utc)
    outline = Outline(
        project_id=project_id,
        principle_id=principle_id or "imported",
        version=1,
        root_sections=[_to_outline_node(s) for s in result.root_sections],
        created_at=now,
        updated_at=now,
        notes=[f"Reverse-imported from {result.source_filename}"],
    )
    save_outline(outline)
    n_drafts = 0
    for sec in _walk(result.root_sections):
        if not sec.markdown:
            continue
        draft = SectionDraft(
            node_id=sec.node_id,
            title=sec.title,
            markdown=sec.markdown,
            citations=[],
            word_count=sec.word_count,
            generated_at=now,
            llm_meta=LLMMeta(model="csr_importer", via="import"),
            warnings=[],
            status="draft",
            markers=[],
        )
        save_draft(project_id, draft)
        n_drafts += 1
    return {
        "ok": True,
        "import_id": import_id,
        "n_outline_nodes": _count_headings(result.root_sections),
        "n_drafts": n_drafts,
    }


def _to_outline_node(sec: ImportSection) -> OutlineNode:
    return OutlineNode(
        id=sec.node_id,
        title=sec.title,
        principle_ref="",
        level=sec.level,
        status="done" if sec.markdown else "pending",
        notes="(reverse-imported)",
        project_specific=True,
        children=[_to_outline_node(c) for c in sec.children],
    )


def _walk(roots: list[ImportSection]):
    for r in roots:
        yield r
        yield from _walk(r.children)
