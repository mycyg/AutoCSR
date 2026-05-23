"""Report routes — generate, status, drafts, regenerate, terminology."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.state import guard_locked

from app.config import data_dir
from app.outline.store import load as load_outline
from app.report import status as status_reg
from app.report.orchestrator import write_all
from app.report.store import (
    assemble_report, delete_draft, list_drafts, load_draft, load_report,
    load_terminology, save_draft, save_report, save_terminology,
)
from app.report.writer_agent import WriterContext, write_section
from app.schemas.outline import OutlineNode
from app.server.ws import publish

logger = logging.getLogger("autocsr.report.routes")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


# ---------------------------------------------------------------------------
# Generate / status / drafts
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/report/generate")
async def generate(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    outline = load_outline(pid)
    if outline is None:
        raise HTTPException(status_code=400, detail="outline not built")

    harmonize = bool(body.get("harmonize", True))
    leaf_limit = body.get("leaf_limit")
    if leaf_limit is not None:
        try:
            leaf_limit = int(leaf_limit)
        except Exception:
            leaf_limit = None
    enable_tools = body.get("enable_tools")
    if enable_tools is not None:
        enable_tools = bool(enable_tools)
    max_tool_turns = int(body.get("max_tool_turns") or 5)

    async def _runner() -> None:
        try:
            try:
                from app.state import default_machine, ProjectState
                default_machine.try_transition(pid, ProjectState.writing,
                                                reason="report.generate")
            except Exception:
                pass
            report = await write_all(
                pid, harmonize=harmonize, leaf_limit=leaf_limit,
                enable_tools=enable_tools, max_tool_turns=max_tool_turns,
            )
            try:
                from app.state import default_machine, ProjectState
                target = ProjectState.harmonized if report.harmonized else ProjectState.writing
                default_machine.try_transition(pid, target,
                                                reason="report.generate done")
            except Exception:
                pass
        except Exception as e:
            logger.exception("report.generate failed")
            status_reg.mark_error(pid, str(e)[:300])
            await publish(pid, "writer.report_error", {"error": str(e)[:300]})

    asyncio.create_task(_runner())
    return {"started": True, "harmonize": harmonize, "leaf_limit": leaf_limit}


@router.get("/projects/{pid}/report/status")
def get_status(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    s = status_reg.get(pid)
    if s is None:
        # Best-effort reconstruct from disk
        drafts = list_drafts(pid)
        outline = load_outline(pid)
        leaves_total = 0
        if outline is not None:
            leaves_total = sum(1 for n in outline.walk() if not n.children)
        return {
            "project_id": pid,
            "outline_version": outline.version if outline else None,
            "leaves_total": leaves_total,
            "leaves_done": sum(1 for d in drafts if d.status != "error"),
            "leaves_errored": sum(1 for d in drafts if d.status == "error"),
            "current_phase": "idle",
            "harmonized": all(d.status == "harmonized" for d in drafts) if drafts else False,
            "total_tokens": {
                "input": sum(d.llm_meta.tokens_in for d in drafts),
                "output": sum(d.llm_meta.tokens_out for d in drafts),
            },
            "total_words": sum(d.word_count for d in drafts),
            "last_event_at": None,
            "error": None,
            "sections": [
                {"node_id": d.node_id, "title": d.title, "status": d.status, "words": d.word_count}
                for d in drafts
            ],
        }
    return s.model_dump()


@router.get("/projects/{pid}/report/drafts")
def list_drafts_endpoint(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    drafts = list_drafts(pid)
    out: list[dict[str, Any]] = []
    for d in drafts:
        out.append({
            "node_id": d.node_id,
            "title": d.title,
            "status": d.status,
            "word_count": d.word_count,
            "n_citations": len(d.citations),
            "generated_at": d.generated_at.isoformat() if d.generated_at else None,
            "warnings": d.warnings,
        })
    return out


@router.get("/projects/{pid}/report/drafts/{node_id}")
def get_draft(pid: str, node_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    d = load_draft(pid, node_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"draft {node_id} not found")
    return d.model_dump()


@router.delete("/projects/{pid}/report/drafts/{node_id}")
def delete_draft_endpoint(pid: str, node_id: str) -> dict[str, bool]:
    _ensure_project(pid)
    return {"ok": delete_draft(pid, node_id)}


@router.post("/projects/{pid}/report/regenerate/{node_id}")
async def regenerate(pid: str, node_id: str, request: Request, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    guard_locked(pid, request)
    outline = load_outline(pid)
    if outline is None:
        raise HTTPException(status_code=400, detail="outline not built")
    node = outline.find(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")
    extra = str(body.get("extra_instructions") or "")
    terminology = load_terminology(pid)

    await publish(pid, "writer.section_start", {
        "node_id": node_id, "title": node.title, "phase": "regenerate",
    })
    try:
        ctx = WriterContext(
            project_id=pid, terminology=terminology, extra_instructions=extra,
        )
        draft = await write_section(pid, node, ctx)
    except Exception as e:
        await publish(pid, "writer.section_error", {"node_id": node_id, "error": str(e)[:200]})
        raise HTTPException(status_code=500, detail=f"regenerate failed: {e}")
    save_draft(pid, draft)
    await publish(pid, "writer.section_done", {
        "node_id": node_id, "title": node.title,
        "words": draft.word_count,
        "tokens_in": draft.llm_meta.tokens_in,
        "tokens_out": draft.llm_meta.tokens_out,
        "latency_ms": draft.llm_meta.latency_ms,
    })
    # Refresh the assembled report on disk so /report returns the new version
    save_report(assemble_report(pid, outline.version, harmonized=False))
    return draft.model_dump()


@router.get("/projects/{pid}/report")
def get_report(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    rep = load_report(pid)
    if rep is None:
        outline = load_outline(pid)
        ver = outline.version if outline else 0
        rep = assemble_report(pid, ver, harmonized=False)
    return rep.model_dump()


# ---------------------------------------------------------------------------
# Terminology
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/terminology")
def get_terminology(pid: str) -> dict[str, str]:
    _ensure_project(pid)
    return load_terminology(pid)


@router.patch("/projects/{pid}/terminology")
def patch_terminology(pid: str, body: dict = Body(...)) -> dict[str, str]:
    _ensure_project(pid)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    return save_terminology(pid, body)
