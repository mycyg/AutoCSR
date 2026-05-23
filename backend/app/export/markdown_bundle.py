"""Markdown bundle export (M19).

Produces a portable zip containing:

  ``README.md``           — project metadata + section index
  ``sections/<id>.md``    — one file per outline node
  ``assets/<id>.json``    — chart_json for each StatBlock referenced
  ``citations.json``      — flat list of citations across all drafts

This format is ideal for handing the source content off to another
authoring tool (Obsidian, Notion, MkDocs, …) or for diff-friendly
version control of the report content.

Output: ``data/projects/<pid>/exports/CSR_<ts>.md.zip``.
"""
from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.analysis import store as analysis_store
from app.config import data_dir
from app.outline.store import load as load_outline
from app.report.store import list_drafts
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import SectionDraft

logger = logging.getLogger("autocsr.export.md_bundle")


@dataclass(frozen=True)
class MdBundleResult:
    path: Path
    filename: str
    size_bytes: int
    n_files: int
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


def _walk(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []

    def _w(n: OutlineNode) -> None:
        out.append(n)
        for c in n.children:
            _w(c)

    for root in outline.root_sections:
        _w(root)
    return out


def _safe_id(node_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]", "_", node_id)


def _hallucination_findings(project_id: str) -> list[dict[str, Any]]:
    try:
        from app.safety.hallucination_guard import project_scan
        return [f.model_dump() for f in project_scan(project_id)]
    except Exception:
        return []


def build_markdown_bundle(
    project_id: str,
    *,
    include_hallucination_warnings: bool = False,
    progress_cb: Callable[[str], None] | None = None,
) -> MdBundleResult:
    outline = load_outline(project_id)
    if outline is None:
        raise RuntimeError(f"project {project_id} has no outline; build one first")

    drafts = list_drafts(project_id)
    drafts_by_id = {d.node_id: d for d in drafts}
    nodes = _walk(outline)
    now = datetime.now()
    proj_name = _project_name(project_id)

    if progress_cb:
        progress_cb("planning")

    # ---- README.md --------------------------------------------------------
    readme_lines = [
        f"# {proj_name} — Clinical Study Report",
        "",
        f"- Project ID: `{project_id}`",
        f"- Generated: {now.isoformat(timespec='seconds')}",
        f"- Sections: {len(nodes)}",
        f"- Drafts: {sum(1 for d in drafts if d.markdown.strip())}",
        f"- Citations: {sum(len(d.citations or []) for d in drafts)}",
        "",
        "## Section index",
        "",
    ]
    for n in nodes:
        readme_lines.append(
            f"- [{n.id} {n.title}](sections/{_safe_id(n.id)}.md)"
        )
    readme_lines.append("")
    readme_lines.append("## Assets")
    readme_lines.append("")
    readme_lines.append(
        "Each StatBlock chart referenced by a section is exported as JSON "
        "under `assets/<stat_id>.json`. Each entry follows the ECharts "
        "options schema and can be rehydrated client-side."
    )
    findings = _hallucination_findings(project_id) if include_hallucination_warnings else []
    if include_hallucination_warnings:
        readme_lines.extend([
            "",
            "## Hallucination warnings",
            "",
            f"- Findings: {len(findings)}",
            "- Details: `hallucination_warnings.json`",
        ])

    readme = "\n".join(readme_lines)

    # ---- Sections ---------------------------------------------------------
    if progress_cb:
        progress_cb("writing_sections")

    section_files: dict[str, str] = {}
    asset_files: dict[str, str] = {}
    all_citations: list[dict[str, Any]] = []
    seen_stat_ids: set[str] = set()
    for n in nodes:
        draft = drafts_by_id.get(n.id)
        header = f"# {n.id}  {n.title}\n\n"
        body = (draft.markdown.strip() if draft and draft.markdown else "*(No content yet.)*\n")
        # Strip a leading H2 dup of the title if present in the draft.
        body = re.sub(r"^##\s+[^\n]+\n+", "", body)
        section_files[f"sections/{_safe_id(n.id)}.md"] = header + body + "\n"
        if not draft:
            continue
        # Citations
        for c in (draft.citations or []):
            all_citations.append({
                "node_id": n.id,
                "ref_code": c.ref_code,
                "type": c.type,
                "locator": c.locator,
                "snippet": (c.snippet or "")[:300],
            })
            if c.type == "stat":
                sid = c.ref_code.removeprefix("Ref<").rstrip(">").split(".")[0]
                if sid and sid not in seen_stat_ids:
                    seen_stat_ids.add(sid)
                    try:
                        blk = analysis_store.get(project_id, sid)
                    except Exception:
                        blk = None
                    if blk is not None:
                        chart = (blk.result_json or {}).get("chart_json") if hasattr(blk, "result_json") else None
                        if chart:
                            asset_files[f"assets/{_safe_id(sid)}.json"] = json.dumps(
                                {
                                    "stat_id": sid,
                                    "title": getattr(blk, "title", ""),
                                    "type": getattr(blk, "analysis_type", ""),
                                    "chart_json": chart,
                                },
                                ensure_ascii=False, indent=2,
                            )

    citations_json = json.dumps(all_citations, ensure_ascii=False, indent=2)

    # ---- Pack zip ---------------------------------------------------------
    if progress_cb:
        progress_cb("packing")

    out_path = _exports_dir(project_id) / f"CSR_{now.strftime('%Y%m%d_%H%M%S')}.md.zip"
    n_files = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", readme); n_files += 1
        for name, payload in section_files.items():
            zf.writestr(name, payload); n_files += 1
        for name, payload in asset_files.items():
            zf.writestr(name, payload); n_files += 1
        # Guarantee assets/ exists even when no charts.
        if not asset_files:
            zf.writestr("assets/.gitkeep", ""); n_files += 1
        zf.writestr("citations.json", citations_json); n_files += 1
        if include_hallucination_warnings:
            zf.writestr(
                "hallucination_warnings.json",
                json.dumps(findings, ensure_ascii=False, indent=2),
            )
            n_files += 1

    size = out_path.stat().st_size
    if progress_cb:
        progress_cb("done")

    return MdBundleResult(
        path=out_path,
        filename=out_path.name,
        size_bytes=size,
        n_files=n_files,
        generated_at=now.isoformat(timespec="seconds"),
    )


__all__ = ["build_markdown_bundle", "MdBundleResult"]
