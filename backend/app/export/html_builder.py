"""HTML export (M19).

Renders the same project content as a single self-contained HTML file with
inline CSS + an ECharts ``<script>`` tag pulled from a public CDN. Every
:class:`StatBlock` whose ``result_json.chart_json`` field is populated
becomes an interactive chart on the page.

Output: ``data/projects/<pid>/exports/CSR_<ts>.html``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import markdown as _md_lib

from app.analysis import store as analysis_store
from app.cleansing import pipeline_io as cleansing_pipeline
from app.config import data_dir
from app.outline.store import load as load_outline
from app.report.store import list_drafts
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import SectionDraft

logger = logging.getLogger("autocsr.export.html")


@dataclass(frozen=True)
class HtmlExportResult:
    path: Path
    filename: str
    size_bytes: int
    n_sections: int
    n_charts: int
    n_citations: int
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


def _walk_in_order(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []

    def _w(n: OutlineNode) -> None:
        out.append(n)
        for c in n.children:
            _w(c)

    for root in outline.root_sections:
        _w(root)
    return out


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


def _gather_cleansing_rows(project_id: str) -> tuple[list[tuple[str, str]], int]:
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
    rows = [(k, str(v)) for k, v in sorted(by_type.items())] or [("(none)", "0")]
    return rows, rule_count


def _gather_analysis_rows(project_id: str) -> list[tuple[str, str, str, str]]:
    try:
        idx = analysis_store.list_blocks(project_id)
    except Exception:
        idx = []
    rows = []
    for s in idx:
        rows.append((
            str(s.get("id") or "")[:12],
            str(s.get("analysis_type") or ""),
            str(s.get("title") or "")[:80],
            ", ".join(s.get("source_files") or [])[:60],
        ))
    return rows or [("(none)", "", "", "")]


def _charts_for_section(project_id: str, draft: SectionDraft | None) -> list[dict]:
    """Return chart configs referenced from the section. Skips silently if
    the StatBlock has no chart_json field."""
    if draft is None:
        return []
    refs = [c.ref_code for c in (draft.citations or []) if c.type == "stat"]
    out: list[dict] = []
    seen = set()
    for ref in refs:
        # ref_code shape "Ref<stat_id>" — strip
        sid = ref.removeprefix("Ref<").rstrip(">")
        sid = sid.split(".")[0]
        if not sid or sid in seen:
            continue
        seen.add(sid)
        try:
            blk = analysis_store.get(project_id, sid)
        except Exception:
            blk = None
        if blk is None:
            continue
        chart = (blk.result_json or {}).get("chart_json") if hasattr(blk, "result_json") else None
        title = getattr(blk, "title", "") or sid
        if chart:
            out.append({
                "id": sid,
                "title": title,
                "config_json": json.dumps(chart, ensure_ascii=False),
            })
    return out


def _markdown_to_html(text: str) -> str:
    if not (text or "").strip():
        return ""
    return _md_lib.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )


# ---------------------------------------------------------------------------
# build_html
# ---------------------------------------------------------------------------


def build_html(
    project_id: str,
    *,
    include_compliance_note: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> HtmlExportResult:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    outline = load_outline(project_id)
    if outline is None:
        raise RuntimeError(f"project {project_id} has no outline; build one first")

    drafts = list_drafts(project_id)
    drafts_by_id = {d.node_id: d for d in drafts}

    if progress_cb:
        progress_cb("building_sections")

    nodes = _walk_in_order(outline)
    sections = []
    n_charts = 0
    for node in nodes:
        draft = drafts_by_id.get(node.id)
        markdown_html = _markdown_to_html(draft.markdown if draft else "")
        # Strip leading H2 duplicate of the section title.
        if markdown_html.startswith("<h2>"):
            end = markdown_html.find("</h2>") + len("</h2>")
            markdown_html = markdown_html[end:].lstrip()
        charts = _charts_for_section(project_id, draft)
        n_charts += len(charts)
        sections.append({
            "id": node.id,
            "title": node.title,
            "level": max(1, min(int(getattr(node, "level", 1) or 1), 4)),
            "markdown_html": markdown_html,
            "has_children": bool(node.children),
            "charts": charts,
        })

    citations = _gather_unique_citations(drafts)
    cleansing_rows, rule_count = _gather_cleansing_rows(project_id)
    analysis_rows = _gather_analysis_rows(project_id)

    if progress_cb:
        progress_cb("rendering")

    now = datetime.now()
    tpl_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "htm"]),
    )
    tpl = env.get_template("report.html.j2")
    rendered = tpl.render(
        project_name=_project_name(project_id),
        version=now.strftime("%Y%m%d-%H%M"),
        generated_at=now.strftime("%Y-%m-%d %H:%M"),
        compliance_note=(
            f"Data cleansed via pipeline v1 with {rule_count} rules."
            if include_compliance_note else ""
        ),
        toc=nodes,
        sections=sections,
        citations=citations,
        cleansing_rows=cleansing_rows,
        analysis_rows=analysis_rows,
    )

    out_path = _exports_dir(project_id) / f"CSR_{now.strftime('%Y%m%d_%H%M%S')}.html"
    out_path.write_text(rendered, encoding="utf-8")
    size = out_path.stat().st_size

    if progress_cb:
        progress_cb("done")

    return HtmlExportResult(
        path=out_path,
        filename=out_path.name,
        size_bytes=size,
        n_sections=len(nodes),
        n_charts=n_charts,
        n_citations=len(citations),
        generated_at=now.isoformat(timespec="seconds"),
    )


__all__ = ["build_html", "HtmlExportResult"]
