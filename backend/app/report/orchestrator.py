"""Three-phase parallel orchestrator for M4 writer agents.

M9 update — :class:`AnalystFuturePool` deduplicates identical natural-language
analyst queries that multiple writers might issue inside the same run. The
pool is passed in via :class:`WriterContext.analyst_pool` and consumed by the
``call_analyst`` builtin tool.


Phases:
    A. background  — outline sections whose top-level chapter id ∈ {1..9}.
                      Mostly no statistical dependencies.
    B. results     — chapter ids ∈ {10, 11, 12}. Heavy StatBlock dependency;
                      run *after* A so terminology stabilises.
    C. discussion  — chapter ids ∈ {13..} plus appendix. Need A + B done.

Inside each phase only **leaf** nodes are written; non-leaf nodes are H-titles
that carry no narrative on their own. Leaves are processed with
``asyncio.gather`` under a ``Semaphore(max_parallel_writers)``.

Errors in one section never abort a phase — the section is marked status=error
and the next one proceeds.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Iterable

from app.agents.writer import WriterAgent
from app.config import settings
from app.outline import store as outline_store
from app.report import status as status_reg
from app.report.store import (
    DEFAULT_TERMINOLOGY, assemble_report, load_terminology,
    save_draft, save_report,
)
from app.report.writer_agent import WriterContext, write_section
from app.schemas.agent import AgentInput
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import ReportDraft, SectionDraft
from app.server.ws import publish

logger = logging.getLogger("autocsr.report.orchestrator")


# ---------------------------------------------------------------------------
# Analyst FuturePool — shared cache of analyst queries across writers
# ---------------------------------------------------------------------------

import hashlib as _hashlib
from typing import Any as _Any


class AnalystFuturePool:
    """Coalesce identical analyst queries into a single sandbox run.

    Two writers that both ask "ADAE 出现频率 top 5 SOC" will share the
    same :class:`asyncio.Future` and therefore the same StatBlock; the
    sandbox only runs once. We emit ``analyst.dedup_hit`` so the frontend
    can show the cache hit.
    """

    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future[_Any]] = {}
        self._requesters: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(query: str, scope: str) -> str:
        norm = (query.strip().lower() + "|" + scope.strip().lower())
        return _hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]

    async def request(self, project_id: str, query: str, scope: str = "all",
                       *, requester: str = "") -> dict[str, _Any]:
        key = self._key(query, scope)
        async with self._lock:
            fut = self._futures.get(key)
            if fut is None:
                fut = asyncio.get_event_loop().create_future()
                self._futures[key] = fut
                self._requesters[key] = [requester] if requester else []
                fresh = True
            else:
                self._requesters.setdefault(key, []).append(requester)
                fresh = False
        if fresh:
            try:
                from app.agents.analyst_agent import run_analyst
                from app.server.ws import publish as _publish

                result = await run_analyst(project_id, query, scope=scope)
                fut.set_result(result)
                return result
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)
                raise
        else:
            from app.server.ws import publish as _publish

            await _publish(project_id, "analyst.dedup_hit", {
                "query": query, "scope": scope,
                "requesters": list(self._requesters.get(key, [])),
                "key": key,
            })
            return await fut


# ---------------------------------------------------------------------------
# Phase classification
# ---------------------------------------------------------------------------

PHASES: tuple[str, ...] = ("background", "results", "discussion")


def _top_chapter(node_id: str) -> int | None:
    head = node_id.split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def _phase_for(node: OutlineNode) -> str:
    top = _top_chapter(node.id)
    if top is None:
        # Non-numeric ids — treat as background by default
        return "background"
    if top <= 9:
        return "background"
    if 10 <= top <= 12:
        return "results"
    return "discussion"


def _leaves(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []
    for n in outline.walk():
        if not n.children:
            out.append(n)
    return out


def _leaves_for_phase(outline: Outline, phase: str) -> list[OutlineNode]:
    return [n for n in _leaves(outline) if _phase_for(n) == phase]


def _parent_of(outline: Outline, node_id: str) -> OutlineNode | None:
    target = node_id
    def _w(parent: OutlineNode | None, n: OutlineNode) -> OutlineNode | None:
        if n.id == target:
            return parent
        for c in n.children:
            r = _w(n, c)
            if r is not None:
                return r
        return None
    for root in outline.root_sections:
        if root.id == target:
            return None
        r = _w(None, root)
        if r is not None:
            return r
    return None


def _summarize_for_parent(node: OutlineNode) -> str:
    parts = [f"父节: {node.id} {node.title}"]
    if node.notes:
        parts.append(node.notes[:240])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def write_all(
    project_id: str,
    *,
    harmonize: bool = True,
    only_phases: Iterable[str] | None = None,
    leaf_limit: int | None = None,
    enable_tools: bool | None = None,
    max_tool_turns: int = 5,
) -> ReportDraft:
    """Run the full multi-agent writer pipeline.

    Args:
        project_id: project id
        harmonize: whether to run the harmonizer pass at the end (default True)
        only_phases: if set, restrict to these phases (useful for partial reruns)
        leaf_limit: cap on total leaves written across all phases (test ergonomics)
    """
    outline = outline_store.load(project_id)
    if outline is None:
        raise RuntimeError("outline not built")

    leaves = _leaves(outline)
    if leaf_limit is not None:
        # Keep first N leaves but preserve outline order
        leaves = leaves[:leaf_limit]
    by_id = {n.id: n for n in outline.walk()}

    status_reg.init(project_id, outline.version, len(leaves))
    await publish(project_id, "writer.batch_start", {
        "total_leaves": len(leaves),
        "phases": list(only_phases) if only_phases else list(PHASES),
        "outline_version": outline.version,
    })

    terminology = load_terminology(project_id) or DEFAULT_TERMINOLOGY
    conf = (settings().get("pipeline") or {})
    max_parallel = int(conf.get("max_parallel_writers", 4) or 4)
    sem = asyncio.Semaphore(max_parallel)

    # Decide whether writers should drive an LLM ↔ tool loop. The env var
    # `CSR_WRITER_TOOLS=1` is the simplest way to opt in from e2e tests; the
    # explicit `enable_tools` keyword wins if provided.
    if enable_tools is None:
        enable_tools = os.environ.get("CSR_WRITER_TOOLS", "").lower() in ("1", "true", "yes")

    # Pool only matters when tools are enabled and we are NOT in mock mode.
    analyst_pool: AnalystFuturePool | None = None
    if enable_tools and os.environ.get("CSR_WRITER_MOCK", "").lower() not in ("1", "true", "yes"):
        analyst_pool = AnalystFuturePool()

    target_phases = list(only_phases) if only_phases else list(PHASES)
    last_section_tail: dict[str, str] = {}  # parent_id -> tail of previous sibling

    for phase in target_phases:
        phase_leaves = [n for n in leaves if _phase_for(n) == phase]
        status_reg.update(project_id, current_phase=phase)
        await publish(project_id, "writer.batch_start", {
            "phase": phase, "leaves_in_phase": len(phase_leaves),
        })
        if not phase_leaves:
            await publish(project_id, "writer.batch_done", {
                "phase": phase, "drafts_count": 0,
            })
            continue

        writer_agent = WriterAgent()

        async def _run_leaf(node: OutlineNode) -> SectionDraft:
            async with sem:
                parent = _parent_of(outline, node.id)
                parent_summary = _summarize_for_parent(parent) if parent else ""
                sibling_tail = last_section_tail.get(parent.id if parent else "", "")
                ctx = WriterContext(
                    project_id=project_id,
                    parent_summary=parent_summary,
                    sibling_tail=sibling_tail,
                    terminology=terminology,
                    enable_tools=bool(enable_tools),
                    max_tool_turns=int(max_tool_turns),
                )
                if analyst_pool is not None:
                    ctx.analyst_pool = analyst_pool
                await publish(project_id, "writer.section_start", {
                    "node_id": node.id, "title": node.title, "phase": phase,
                })
                try:
                    # Run through BaseAgent so agent.start/done events emit.
                    # The Pydantic model dump cannot carry the live FuturePool
                    # object — inject it separately under "context" so the
                    # WriterAgent wrapper can re-attach.
                    ctx_dict = ctx.model_dump(exclude={"analyst_pool"})
                    if analyst_pool is not None:
                        ctx_dict["analyst_pool"] = analyst_pool
                    ai = AgentInput(
                        project_id=project_id,
                        payload={"node": node.model_dump(),
                                  "context": ctx_dict},
                        meta={"node_id": node.id, "phase": phase},
                    )
                    ao = await writer_agent.run(ai)
                    draft = SectionDraft.model_validate(ao.result)
                except Exception as e:  # noqa: BLE001
                    logger.exception("writer crashed on %s", node.id)
                    err_draft = SectionDraft(
                        node_id=node.id, title=node.title,
                        markdown=f"## {node.title}\n\n(writer error: {e})",
                        generated_at=datetime.now(timezone.utc),
                        warnings=[f"writer_crash:{type(e).__name__}:{str(e)[:160]}"],
                        status="error",
                    )
                    save_draft(project_id, err_draft)
                    outline_store.update_node(project_id, node.id, {"status": "pending"})
                    status_reg.add_section(project_id, node.id, node.title,
                                           status="error", words=0, error=str(e)[:200])
                    await publish(project_id, "writer.section_error", {
                        "node_id": node.id, "error": str(e)[:200],
                    })
                    return err_draft
                save_draft(project_id, draft)
                outline_store.update_node(project_id, node.id, {"status": "done"})
                if parent is not None:
                    # store last 1-2 sentences for next sibling
                    tail = draft.markdown.strip().splitlines()[-1] if draft.markdown.strip() else ""
                    last_section_tail[parent.id] = tail[-280:]
                status_reg.add_section(
                    project_id, node.id, node.title,
                    status="done" if draft.status != "error" else "error",
                    words=draft.word_count,
                    tokens_in=draft.llm_meta.tokens_in,
                    tokens_out=draft.llm_meta.tokens_out,
                )
                await publish(project_id, "writer.section_done", {
                    "node_id": node.id, "title": node.title,
                    "words": draft.word_count,
                    "tokens_in": draft.llm_meta.tokens_in,
                    "tokens_out": draft.llm_meta.tokens_out,
                    "latency_ms": draft.llm_meta.latency_ms,
                    "warnings": draft.warnings,
                })
                return draft

        results = await asyncio.gather(*[_run_leaf(n) for n in phase_leaves],
                                       return_exceptions=False)
        await publish(project_id, "writer.batch_done", {
            "phase": phase, "drafts_count": len(results),
        })

    # Assemble + optional harmonize
    report = assemble_report(project_id, outline.version, harmonized=False)
    if harmonize:
        status_reg.update(project_id, current_phase="harmonize")
        from app.agents.writer import HarmonizerAgent
        from app.report.harmonizer import harmonize as _harmonize
        # Run via BaseAgent so a single agent.start/done shows up; the inner
        # harmonize() still owns the actual rewrite logic.
        harm_agent = HarmonizerAgent()
        ai = AgentInput(
            project_id=project_id,
            payload={"report": report, "outline": outline},
            meta={"leaves_total": report.leaves_total},
        )
        # HarmonizerAgent wraps harmonize_fn directly; we still pass `by_id`
        # via the underlying function so behaviour stays identical to M4/M5.
        report = await _harmonize(project_id, report, outline, by_id)
        # Emit a synthetic agent.done so logs stay consistent (no double-LLM)
        try:
            harm_agent.logger.info("agent.done", agent="Harmonizer",
                                    project_id=project_id,
                                    leaves_total=report.leaves_total,
                                    harmonized=report.harmonized)
        except Exception:
            pass
    save_report(report)
    status_reg.update(project_id, current_phase="done", harmonized=report.harmonized)
    # Invalidate alerts cache so writer errors are reflected in the bar
    try:
        from app.server.routes.alerts import invalidate as _alerts_invalidate
        _alerts_invalidate(project_id)
        await publish(project_id, "alerts.updated", {"source": "writer"})
    except Exception:
        pass
    await publish(project_id, "writer.report_done", {
        "harmonized": report.harmonized,
        "leaves_total": report.leaves_total,
        "leaves_done": report.leaves_done,
        "total_words": report.total_words,
        "tokens_in": report.total_tokens.input,
        "tokens_out": report.total_tokens.output,
    })
    return report
