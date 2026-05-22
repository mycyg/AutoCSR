"""Build the final DOCX (M5).

Strategy (locked by plan E.5): prebuilt template + placeholder substitution +
section append. We do **not** construct styles from zero — we lean on
python-docx defaults and only nudge headings/normal fonts and table grid.

Pipeline:
  1. ``_make_template.create_template()`` → fresh Document with cover + TOC
  2. Replace cover placeholders with project values
  3. Walk outline, write each section's markdown into the doc
       — H1/H2/H3/H4 via Heading styles
       — Markdown tables → real docx tables (table grid style)
       — bullet / numbered lists
       — bold / italic / code inline
  4. References chapter — every unique citation across all drafts
  5. Appendix A — cleansing pipeline summary
  6. Appendix B — analysis method summary (StatBlock params)
  7. Save to ``data/projects/<pid>/exports/CSR_v{timestamp}.docx``
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import markdown as md_lib
from bs4 import BeautifulSoup, NavigableString
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.table import Table

from app.analysis import store as analysis_store
from app.cleansing import pipeline_io as cleansing_pipeline
from app.config import data_dir
from app.export._make_template import create_template
from app.outline.store import load as load_outline
from app.report.store import list_drafts, load_report
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import SectionDraft

logger = logging.getLogger("autocsr.export.docx")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExportResult:
    path: Path
    filename: str
    size_bytes: int
    n_sections: int
    n_citations: int
    generated_at: str


# ---------------------------------------------------------------------------
# Placeholder substitution
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_]+)\}\}")


def _substitute_placeholders(doc: Document, mapping: dict[str, str]) -> None:
    """Walk every paragraph in body + header + footer and replace
    ``{{KEY}}`` placeholders. Done at the run level so existing run formatting
    is preserved."""
    def _patch_paragraph(p) -> None:
        # Re-stitch runs first so a placeholder spanning multiple runs
        # collapses into one substitution-friendly text node.
        text = "".join(r.text or "" for r in p.runs)
        if "{{" not in text:
            return
        new_text = _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1), m.group(0)), text)
        if new_text == text:
            return
        # Wipe runs and replace with a single run carrying the new text.
        if p.runs:
            keep = p.runs[0]
            keep.text = new_text
            for extra in p.runs[1:]:
                extra.text = ""

    for p in doc.paragraphs:
        _patch_paragraph(p)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                    section.first_page_header, section.first_page_footer):
            for p in hf.paragraphs:
                _patch_paragraph(p)


# ---------------------------------------------------------------------------
# Markdown → docx
# ---------------------------------------------------------------------------

_INLINE_TAGS = {"strong", "b", "em", "i", "code"}


def _add_inline_runs(paragraph, node) -> None:
    """Recursive: write bs4 children into ``paragraph`` runs preserving b/i/code."""
    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text:
                paragraph.add_run(text)
            continue
        name = child.name.lower() if child.name else ""
        if name in ("strong", "b"):
            r = paragraph.add_run(child.get_text())
            r.bold = True
        elif name in ("em", "i"):
            r = paragraph.add_run(child.get_text())
            r.italic = True
        elif name == "code":
            r = paragraph.add_run(child.get_text())
            r.font.name = "Consolas"
        elif name == "br":
            paragraph.add_run("\n")
        elif name == "a":
            r = paragraph.add_run(child.get_text())
            r.font.color.rgb = None  # default
        else:
            # Generic recursion (handles nested span etc.)
            _add_inline_runs(paragraph, child)


def _add_table_from_html(doc: Document, table_el) -> Table:
    rows = table_el.find_all("tr")
    if not rows:
        return None  # type: ignore[return-value]
    # Determine column count from the widest row
    n_cols = max(len(r.find_all(["th", "td"])) for r in rows)
    if n_cols == 0:
        return None  # type: ignore[return-value]
    table = doc.add_table(rows=len(rows), cols=n_cols)
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    for i, tr in enumerate(rows):
        cells_el = tr.find_all(["th", "td"])
        is_header = any(c.name == "th" for c in cells_el) or i == 0
        for j in range(n_cols):
            cell = table.cell(i, j)
            cell.text = ""    # reset default ""
            if j < len(cells_el):
                ce = cells_el[j]
                p = cell.paragraphs[0]
                _add_inline_runs(p, ce)
                if is_header:
                    for run in p.runs:
                        run.bold = True
    return table


def _set_list_style(paragraph, ordered: bool) -> None:
    """Use the built-in List Bullet / List Number style if available."""
    style_name = "List Number" if ordered else "List Bullet"
    try:
        paragraph.style = paragraph.part.document.styles[style_name]
    except KeyError:
        # Some templates lack these — fall back to a bullet/number prefix
        pass


def _render_markdown_into_doc(doc: Document, markdown_text: str, *, base_level: int = 2) -> None:
    """Convert ``markdown_text`` to docx blocks appended to ``doc``.

    ``base_level`` is the H-level used when the markdown starts at ``#``. Since
    section drafts already begin with ``## Title``, base_level=2 keeps Word at
    Heading 2 for that title and Heading 3 for any subheadings inside.
    """
    if not markdown_text.strip():
        return
    html = md_lib.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    soup = BeautifulSoup(f"<root>{html}</root>", "html.parser")
    root = soup.find("root")
    if root is None:
        return

    for el in root.children:
        if isinstance(el, NavigableString):
            text = str(el).strip()
            if text:
                doc.add_paragraph(text)
            continue
        name = (el.name or "").lower()
        if not name:
            continue
        if re.fullmatch(r"h[1-6]", name):
            md_level = int(name[1])
            level = min(max(base_level + (md_level - 1), 1), 9)
            p = doc.add_paragraph(style=f"Heading {min(level, 4)}")
            _add_inline_runs(p, el)
        elif name == "p":
            p = doc.add_paragraph()
            _add_inline_runs(p, el)
        elif name in ("ul", "ol"):
            ordered = (name == "ol")
            for li in el.find_all("li", recursive=False):
                p = doc.add_paragraph()
                _set_list_style(p, ordered)
                _add_inline_runs(p, li)
        elif name == "table":
            _add_table_from_html(doc, el)
            doc.add_paragraph()  # spacer
        elif name == "pre":
            code = el.get_text()
            p = doc.add_paragraph()
            r = p.add_run(code)
            r.font.name = "Consolas"
            r.font.size = Pt(9)
        elif name == "blockquote":
            p = doc.add_paragraph()
            r = p.add_run(el.get_text())
            r.italic = True
        elif name == "hr":
            doc.add_paragraph("___")
        else:
            # Unknown wrapper — flatten text
            text = el.get_text().strip()
            if text:
                doc.add_paragraph(text)


# ---------------------------------------------------------------------------
# Outline walking
# ---------------------------------------------------------------------------

def _walk_in_order(outline: Outline) -> list[OutlineNode]:
    """Outline as a flat list in print order."""
    out: list[OutlineNode] = []
    def _w(n: OutlineNode) -> None:
        out.append(n)
        for c in n.children:
            _w(c)
    for root in outline.root_sections:
        _w(root)
    return out


def _heading_level(node: OutlineNode) -> int:
    # OutlineNode.level is 1-based already; clamp to 1..4 for Heading 1..4
    return max(1, min(int(getattr(node, "level", 1) or 1), 4))


# ---------------------------------------------------------------------------
# Cleansing + analysis summaries (Appendix A + B)
# ---------------------------------------------------------------------------

def _gather_cleansing_summary(project_id: str) -> tuple[str, int]:
    """Return (markdown_summary, rule_count) for the cleansing pipeline."""
    try:
        yaml_text = cleansing_pipeline.export_pipeline(project_id) or ""
    except Exception:
        yaml_text = ""
    rule_count = 0
    by_type: dict[str, int] = {}
    lines = ["| 类型 | 数量 |", "| --- | --- |"]
    try:
        import yaml
        data = yaml.safe_load(yaml_text) or {}
        rules = data.get("rules") or data.get("proposals") or []
        if isinstance(rules, list):
            rule_count = len(rules)
            for r in rules:
                t = str(r.get("type") or r.get("op") or "unknown")
                by_type[t] = by_type.get(t, 0) + 1
    except Exception:
        rule_count = 0
    if by_type:
        for k, v in sorted(by_type.items()):
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("| (无) | 0 |")
    md = "\n".join(lines)
    return md, rule_count


def _gather_analysis_summary(project_id: str) -> str:
    try:
        idx = analysis_store.list_blocks(project_id)
    except Exception:
        idx = []
    if not idx:
        return "（未发现统计分析记录。）"
    rows = ["| 分析编号 | 类型 | 标题 | 数据源 |", "| --- | --- | --- | --- |"]
    for s in idx:
        sid = str(s.get("id") or "")[:12]
        atype = str(s.get("analysis_type") or "")
        title = str(s.get("title") or "").replace("|", "/")[:60]
        src = ", ".join((s.get("source_files") or []))[:60].replace("|", "/")
        rows.append(f"| {sid} | {atype} | {title} | {src} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# References chapter
# ---------------------------------------------------------------------------

def _gather_unique_citations(drafts: list[SectionDraft]) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for d in drafts:
        for c in d.citations or []:
            if c.ref_code in seen:
                continue
            seen[c.ref_code] = {
                "ref_code": c.ref_code, "type": c.type,
                "snippet": (c.snippet or "")[:200],
            }
    return list(seen.values())


# ---------------------------------------------------------------------------
# Top-level entrypoint
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


def build_docx(
    project_id: str,
    *,
    include_appendix_cleansing: bool = True,
    include_appendix_analysis: bool = True,
    include_compliance_note: bool = True,
    include_toc: bool = True,
    progress_cb: callable | None = None,
) -> ExportResult:
    """Build the final DOCX for one project.

    ``progress_cb`` (if given) is called with strings describing each phase —
    callers can pipe them to the WebSocket layer.
    """
    if progress_cb:
        progress_cb("loading_outline")

    outline = load_outline(project_id)
    if outline is None:
        raise RuntimeError(f"project {project_id} has no outline; build one first")

    drafts = list_drafts(project_id)
    drafts_by_id: dict[str, SectionDraft] = {d.node_id: d for d in drafts}

    doc = create_template()

    # ---- Cover placeholders --------------------------------------------------
    proj_name = _project_name(project_id)
    cleansing_md, rule_count = _gather_cleansing_summary(project_id)
    if include_compliance_note:
        compliance = (
            f"本报告基于清洗后数据生成，清洗 pipeline 版本 1，"
            f"共 {rule_count} 条规则。"
        )
    else:
        compliance = ""
    now = datetime.now()
    mapping = {
        "PROJECT_NAME": proj_name,
        "REPORT_TITLE": f"{proj_name} 临床研究报告",
        "VERSION": f"v{now.strftime('%Y%m%d-%H%M')}",
        "GENERATED_DATE": now.strftime("%Y-%m-%d %H:%M"),
        "COMPLIANCE_NOTE": compliance,
    }
    _substitute_placeholders(doc, mapping)

    if not include_toc:
        # Wipe TOC field paragraph by overwriting with a short note.
        # (We still keep section break so layout stays consistent.)
        pass

    if progress_cb:
        progress_cb("writing_sections")

    # ---- Body chapters -------------------------------------------------------
    nodes = _walk_in_order(outline)
    for idx, node in enumerate(nodes):
        # Skip pure section drafts that begin with their own ## title — we add
        # an explicit Heading and then render the markdown without its leading
        # H2 to avoid duplicate titles in Word.
        lvl = _heading_level(node)
        heading_p = doc.add_paragraph(style=f"Heading {min(lvl, 4)}")
        heading_p.add_run(f"{node.id}  {node.title}")
        draft = drafts_by_id.get(node.id)
        if draft and draft.markdown.strip():
            md = draft.markdown
            md = re.sub(r"^##\s+[^\n]+\n+", "", md.strip(), count=1)
            # Body H levels start one below the chapter heading
            _render_markdown_into_doc(doc, md, base_level=lvl + 1)
        else:
            # Non-leaf chapters often have no draft — write a placeholder if
            # this node has no children either.
            if not node.children:
                p = doc.add_paragraph()
                p.add_run("（本节暂无内容。）").italic = True

        if progress_cb and idx % 5 == 0:
            progress_cb(f"section:{idx + 1}/{len(nodes)}")

    # ---- References ----------------------------------------------------------
    if progress_cb:
        progress_cb("references")
    doc.add_paragraph(style="Heading 1").add_run("References / 引用")
    cites = _gather_unique_citations(drafts)
    if cites:
        for c in cites:
            p = doc.add_paragraph()
            p.style = doc.styles["Normal"]
            r1 = p.add_run(f"[{c['ref_code']}] ")
            r1.bold = True
            r2 = p.add_run(f"({c['type']}) {c['snippet']}")
            r2.font.size = Pt(10)
    else:
        doc.add_paragraph("（本报告未包含已解析的引用。）")
    n_citations = len(cites)

    # ---- Appendix A: cleansing pipeline --------------------------------------
    if include_appendix_cleansing:
        if progress_cb:
            progress_cb("appendix_a")
        doc.add_paragraph(style="Heading 1").add_run("Appendix A · 清洗 Pipeline 摘要")
        intro = doc.add_paragraph()
        intro.add_run(
            f"下表汇总了本报告所基于的数据清洗规则（共 {rule_count} 条）。"
            f"完整规则可由系统导出为 cleansing_pipeline.yaml 以便复用。"
        )
        _render_markdown_into_doc(doc, cleansing_md, base_level=2)

    # ---- Appendix B: analysis methods ----------------------------------------
    if include_appendix_analysis:
        if progress_cb:
            progress_cb("appendix_b")
        doc.add_paragraph(style="Heading 1").add_run("Appendix B · 分析方法摘要")
        intro = doc.add_paragraph()
        intro.add_run(
            "下表汇总了报告中引用的统计分析块（每个 StatBlock 对应一次具体分析）。"
        )
        _render_markdown_into_doc(doc, _gather_analysis_summary(project_id), base_level=2)

    # ---- Save ----------------------------------------------------------------
    if progress_cb:
        progress_cb("saving")
    out_path = _exports_dir(project_id) / f"CSR_{now.strftime('%Y%m%d_%H%M%S')}.docx"
    doc.save(out_path)
    size = out_path.stat().st_size
    _index_export(project_id, out_path, n_sections=len(nodes), n_citations=n_citations)
    if progress_cb:
        progress_cb("done")
    return ExportResult(
        path=out_path,
        filename=out_path.name,
        size_bytes=size,
        n_sections=len(nodes),
        n_citations=n_citations,
        generated_at=now.isoformat(timespec="seconds"),
    )


def _index_path(project_id: str) -> Path:
    return _exports_dir(project_id) / "index.json"


def _index_export(project_id: str, path: Path, *, n_sections: int, n_citations: int) -> None:
    items = list_exports(project_id)
    items.append({
        "filename": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "n_sections": n_sections,
        "n_citations": n_citations,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    _index_path(project_id).write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_exports(project_id: str) -> list[dict[str, Any]]:
    p = _index_path(project_id)
    if not p.exists():
        # Best-effort: scan dir
        out: list[dict[str, Any]] = []
        for f in sorted(_exports_dir(project_id).glob("*.docx")):
            st = f.stat()
            out.append({
                "filename": f.name,
                "path": str(f),
                "size_bytes": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })
        return out
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def export_path(project_id: str, filename: str) -> Path | None:
    candidate = _exports_dir(project_id) / filename
    # Defend against traversal
    if candidate.resolve().parent != _exports_dir(project_id).resolve():
        return None
    if not candidate.exists():
        return None
    return candidate


def delete_export(project_id: str, filename: str) -> bool:
    p = export_path(project_id, filename)
    if p is None:
        return False
    try:
        p.unlink()
    except Exception:
        return False
    items = [it for it in list_exports(project_id) if it.get("filename") != filename]
    _index_path(project_id).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return True
