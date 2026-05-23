"""M21 — Statistical Analysis Plan (SAP) docx → outline stat_hints.

The SAP usually has Heading 1/2/3 sections such as "Statistical Methods",
"Analysis Populations", "Efficacy Analysis", "Safety Analysis". We walk
the document headings, identify the analysis-relevant chapters, and
append each chapter's first 1-3 paragraphs (truncated to 280 chars) as
``stat_hints`` on the matching outline node — falling back to a new
``project_specific`` analysis node when no outline exists yet.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("autocsr.ingestion.sap")


_ANALYSIS_KEYWORDS = (
    "statistical method", "analysis population", "efficacy analysis",
    "safety analysis", "primary analysis", "secondary analysis",
    "subgroup analysis", "missing data", "interim analysis",
    "sample size", "pharmacokinetic", "stat method", "统计",
    "分析方法", "疗效分析", "安全性分析", "亚组分析",
)


class SAPSection(BaseModel):
    title: str
    level: int
    hint: str
    paragraphs: list[str] = Field(default_factory=list)


class SAPImportResult(BaseModel):
    project_id: str
    source_filename: str
    n_sections_total: int
    analysis_sections: list[SAPSection]
    hints_attached_to_nodes: int
    used_fallback: bool = False
    notes: list[str] = Field(default_factory=list)


def _parse_docx(path: Path) -> list[tuple[int, str, list[str]]]:
    """Return [(level, heading_text, body_paragraphs[]), ...]."""
    try:
        from docx import Document
    except Exception:
        return []
    out: list[tuple[int, str, list[str]]] = []
    try:
        doc = Document(str(path))
    except Exception as e:
        logger.warning("sap_docx_open_failed: %s", e)
        return []
    cur: tuple[int, str, list[str]] | None = None
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        style_name = (para.style.name or "") if para.style else ""
        m = re.match(r"Heading\s*(\d)", style_name, flags=re.IGNORECASE)
        if m:
            level = int(m.group(1))
            if cur is not None:
                out.append(cur)
            cur = (level, text, [])
        else:
            if cur is None:
                cur = (1, "Front matter", [])
            cur[2].append(text)
    if cur is not None:
        out.append(cur)
    return out


def _is_analysis_heading(heading: str) -> bool:
    lower = heading.lower()
    return any(kw in lower for kw in _ANALYSIS_KEYWORDS)


def import_sap(project_id: str, docx_path: str | Path,
                source_filename: str | None = None) -> SAPImportResult:
    p = Path(docx_path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    sections = _parse_docx(p)
    analysis_sections: list[SAPSection] = []
    for level, heading, paragraphs in sections:
        if not _is_analysis_heading(heading):
            continue
        first_paras = paragraphs[:3]
        hint = " ".join(first_paras)[:280] if first_paras else heading
        analysis_sections.append(SAPSection(
            title=heading, level=level, hint=hint, paragraphs=first_paras,
        ))
    notes_list: list[str] = []
    # Attach hints onto the project outline -------------------------------
    attached = 0
    used_fallback = False
    try:
        from app.outline.store import load as load_outline, save as save_outline
        outline = load_outline(project_id)
        if outline is None:
            used_fallback = True
            notes_list.append("no outline yet — hints staged for later attach")
        else:
            # walk all nodes; match by title prefix or analysis keyword
            def _walk(node, fn):
                fn(node)
                for ch in node.children or []:
                    _walk(ch, fn)

            all_nodes: list[Any] = []
            for root in outline.root_sections or []:
                _walk(root, all_nodes.append)
            for sec in analysis_sections:
                # try exact title token match, else fall back to any node
                # with "analysis" / "statistical" in the title.
                token = sec.title.split()[0].lower() if sec.title else ""
                target = None
                for n in all_nodes:
                    if token and token in (n.title or "").lower():
                        target = n
                        break
                if target is None:
                    for n in all_nodes:
                        nt = (n.title or "").lower()
                        if "analysis" in nt or "statistical" in nt or "stat" in nt:
                            target = n
                            break
                if target is None:
                    continue
                hints = list(getattr(target, "stat_hints", None) or [])
                if sec.hint and sec.hint not in hints:
                    hints.append("[SAP] " + sec.hint)
                    target.stat_hints = hints  # type: ignore[attr-defined]
                    attached += 1
            save_outline(project_id, outline)
    except Exception as e:
        logger.warning("sap_outline_attach_failed: %s", e)
        used_fallback = True
        notes_list.append(f"outline attach failed: {e}")
    # Always persist raw extract as a side artefact -----------------------
    try:
        from app.config import data_dir
        notes_dir = data_dir() / "projects" / project_id / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        (notes_dir / "sap.json").write_text(
            _json.dumps({
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "source": source_filename or p.name,
                "n_sections_total": len(sections),
                "analysis_sections": [
                    {"title": s.title, "level": s.level, "hint": s.hint}
                    for s in analysis_sections
                ],
                "attached": attached,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return SAPImportResult(
        project_id=project_id,
        source_filename=source_filename or p.name,
        n_sections_total=len(sections),
        analysis_sections=analysis_sections,
        hints_attached_to_nodes=attached,
        used_fallback=used_fallback,
        notes=notes_list,
    )
