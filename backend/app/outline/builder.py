"""Outline builder — turn a Principle YAML + project StatBlocks + literature
corpus into a project-specific :class:`app.schemas.outline.Outline`.

Design choices (per plan):
  - The principle skeleton is preserved verbatim (id, title, requirements, stat_hints)
    so downstream M4 writers can still resolve ICH E3 section numbers.
  - Each principle section becomes one OutlineNode. project_specific=False.
  - For every section we attempt to bind:
      * stat_refs        — pick StatBlocks whose analysis_type matches the
                            section's stat hints (heuristic table below).
      * literature_refs  — top-3 corpus hits searching `<title> + stat_hints`.
  - LLM (outline_llm tier) is asked, *section-by-section* (small payload), to
    contribute a one-line `notes` field and optionally suggest one extra
    project-specific child section. When the LLM is unavailable, we degrade to
    purely heuristic binding so e2e tests stay offline.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.analysis.store import list_blocks as list_stats
from app.corpus.index import search as corpus_search
from app.principles import Principle, PrincipleSection, load_principle
from app.schemas.outline import Outline, OutlineNode
from app.schemas.stats import AnalysisType
from app.outline.store import next_version, save as save_outline

logger = logging.getLogger("autocsr.outline.builder")


# ---------------------------------------------------------------------------
# Section ID -> analysis type binding (heuristic)
# ---------------------------------------------------------------------------

# ICH E3 chapter conventions:
#   10  Study Subjects / Disposition / Demographics    -> descriptive (baseline)
#   11  Efficacy Evaluation                            -> inferential / survival
#   12  Safety Evaluation                              -> safety
def _section_analysis_kinds(section_id: str, title: str) -> list[AnalysisType]:
    sid = section_id.strip()
    t = title.lower()
    kinds: list[AnalysisType] = []
    if sid.startswith("10") or "baseline" in t or "demograph" in t or "disposition" in t or "人口学" in title or "基线" in title:
        kinds.append("descriptive")
    if sid.startswith("11") or "efficacy" in t or "endpoint" in t or "primary" in t or "secondary" in t or "有效性" in title or "疗效" in title:
        kinds.append("inferential")
        kinds.append("survival")
    if sid.startswith("12") or "safety" in t or "adverse" in t or "ae" in t or "安全性" in title or "不良事件" in title:
        kinds.append("safety")
    return kinds


def _bind_stat_refs(section_id: str, title: str, stats_idx: list[dict[str, Any]]) -> list[str]:
    """Pick stat blocks whose analysis_type fits this section."""
    kinds = _section_analysis_kinds(section_id, title)
    if not kinds:
        return []
    matched = [s for s in stats_idx if s.get("analysis_type") in kinds]
    return [s["ref_code"] for s in matched if s.get("ref_code")]


def _bind_literature_refs(project_id: str, title: str, hints: list[str], top_k: int = 3) -> list[str]:
    """Top-k literature blocks for this section."""
    query = title
    if hints:
        query = f"{title} " + " ".join(hints[:3])
    try:
        hits = corpus_search(project_id, query, types=("literature",), top_k=top_k)
    except Exception:
        return []
    return [h.ref_code for h in hits]


# ---------------------------------------------------------------------------
# LLM enrichment (best-effort, optional)
# ---------------------------------------------------------------------------

_NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "notes": {"type": "string"},
        "extra_children": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    "required": ["notes"],
}


def _llm_enrich_section(
    principle_id: str,
    section: PrincipleSection,
    bound_stats: list[dict[str, Any]],
    bound_lit: list[str],
) -> dict[str, Any] | None:
    """Best-effort LLM ask. Returns None on any failure (caller falls back)."""
    try:
        from app.llm.ark_client import responses_json
        from app.llm.policy import outline_llm
        from app.config import settings
        if not (settings().get("llm") or {}).get("api_key"):
            return None
    except Exception:
        return None
    sys_msg = (
        "You help authors of an ICH E3 clinical study report. For a single "
        "section, write one Chinese note (1-2 sentences) summarising what the "
        "writer should emphasise given the available data, and optionally "
        "propose ONE extra child sub-section if the bound data demands it. "
        "Output JSON only."
    )
    stats_payload = [{
        "title": s.get("title"), "type": s.get("analysis_type"),
    } for s in bound_stats[:5]]
    user_msg = (
        f"Principle: {principle_id}\n"
        f"Section: {section.id} {section.title}\n"
        f"Requirements: {section.requirements[:5]}\n"
        f"Stat hints: {section.stat_hints}\n"
        f"Bound stats: {stats_payload}\n"
        f"Bound literature refs: {bound_lit[:3]}\n"
    )
    try:
        out = responses_json(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": user_msg}],
            _NOTE_SCHEMA,
            temperature=outline_llm().temperature,
            max_tokens=600,
            reasoning_effort=outline_llm().reasoning_effort,
            timeout=outline_llm().timeout,
        )
        return out
    except Exception as e:
        logger.debug("outline LLM skipped for %s: %s", section.id, e)
        return None


# ---------------------------------------------------------------------------
# Skeleton construction
# ---------------------------------------------------------------------------

def _build_node(
    section: PrincipleSection,
    principle_id: str,
    project_id: str,
    stats_idx: list[dict[str, Any]],
    level: int,
    use_llm: bool,
) -> OutlineNode:
    stat_refs = _bind_stat_refs(section.id, section.title, stats_idx)
    bound_stats = [s for s in stats_idx if s.get("ref_code") in stat_refs]
    lit_refs = _bind_literature_refs(project_id, section.title, section.stat_hints)

    extra_children: list[OutlineNode] = []
    notes_text = ""
    if use_llm and not section.children:           # only enrich leaf-ish nodes
        enriched = _llm_enrich_section(principle_id, section, bound_stats, lit_refs)
        if enriched:
            notes_text = str(enriched.get("notes") or "").strip()
            for ec in enriched.get("extra_children", []) or []:
                t = str(ec.get("title") or "").strip()
                if t:
                    extra_children.append(OutlineNode(
                        id=f"{section.id}.x{len(extra_children) + 1}",
                        title=t,
                        principle_ref=f"Ref{principle_id}.S{section.id}",
                        level=min(level + 1, 6),
                        stat_hints=[],
                        notes=str(ec.get("rationale") or ""),
                        project_specific=True,
                    ))

    children = [
        _build_node(c, principle_id, project_id, stats_idx, level + 1, use_llm)
        for c in section.children
    ] + extra_children

    return OutlineNode(
        id=section.id,
        title=section.title,
        principle_ref=f"Ref{principle_id}.S{section.id}",
        level=level,
        stat_hints=list(section.stat_hints),
        stat_refs=stat_refs,
        literature_refs=lit_refs,
        notes=notes_text,
        project_specific=False,
        children=children,
        status="pending",
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def build(project_id: str, principle_id: str, use_llm: bool | None = None) -> Outline:
    """Build & persist a fresh outline version for ``project_id``.

    ``use_llm`` defaults to True when LLM credentials are configured.
    """
    principle: Principle = await asyncio.to_thread(load_principle, principle_id)
    stats_idx = await asyncio.to_thread(list_stats, project_id)

    if use_llm is None:
        try:
            from app.config import settings
            use_llm = bool((settings().get("llm") or {}).get("api_key"))
        except Exception:
            use_llm = False

    # Build tree section-by-section (sync code path; LLM calls inside are sync
    # too but already short — fine to await in a thread).
    def _all_nodes() -> list[OutlineNode]:
        return [
            _build_node(s, principle_id, project_id, stats_idx, level=1, use_llm=use_llm)
            for s in principle.sections
        ]

    root_sections = await asyncio.to_thread(_all_nodes)

    now = datetime.now(timezone.utc)
    version = await asyncio.to_thread(next_version, project_id)
    outline = Outline(
        project_id=project_id,
        principle_id=principle_id,
        version=version,
        root_sections=root_sections,
        created_at=now,
        updated_at=now,
        notes=[f"built from {principle_id} v{principle.meta.version}",
               f"stats_available={len(stats_idx)}"],
    )
    await asyncio.to_thread(save_outline, outline)
    return outline
