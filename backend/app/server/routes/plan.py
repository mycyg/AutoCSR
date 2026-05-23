"""Plan-first writing routes (M10)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.config import data_dir
from app.outline.store import load as load_outline
from app.report.plan_first import (
    PlanContext, list_plans, load_plan, make_plan, patch_plan, refine_to_draft,
)
from app.report.store import load_terminology
from app.report.writer_agent import WriterContext
from app.server.ws import publish

logger = logging.getLogger("autocsr.routes.plan")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/report/plan/{node_id:path}")
async def create_plan(pid: str, node_id: str,
                       body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    outline = load_outline(pid)
    if outline is None:
        raise HTTPException(status_code=400, detail="outline not built")
    node = outline.find(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")
    ctx = PlanContext(
        extra_instructions=str(body.get("extra_instructions") or ""),
        max_points=int(body.get("max_points") or 8),
    )
    await publish(pid, "plan.start", {"node_id": node_id})
    try:
        plan = await make_plan(pid, node, ctx)
    except Exception as e:  # noqa: BLE001
        await publish(pid, "plan.error", {"node_id": node_id, "error": str(e)[:200]})
        raise HTTPException(status_code=500, detail=f"make_plan failed: {e}")
    await publish(pid, "plan.done", {
        "node_id": node_id, "n_points": len(plan.points),
        "version": plan.version,
    })
    return plan.model_dump()


@router.get("/projects/{pid}/report/plan/{node_id:path}")
def get_plan(pid: str, node_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    plan = load_plan(pid, node_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan {node_id} not found")
    return plan.model_dump()


@router.patch("/projects/{pid}/report/plan/{node_id:path}")
def update_plan(pid: str, node_id: str,
                 body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    points = body.get("points")
    notes = body.get("notes")
    plan = patch_plan(pid, node_id,
                       points=points if isinstance(points, list) else None,
                       notes=notes if isinstance(notes, str) else None)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan {node_id} not found")
    return plan.model_dump()


@router.get("/projects/{pid}/report/plans")
def list_all_plans(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    out = []
    for p in list_plans(pid):
        out.append({
            "node_id": p.node_id,
            "title": p.title,
            "n_points": len(p.points),
            "n_accepted": sum(1 for pt in p.points if pt.status == "accepted"),
            "version": p.version,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return out


@router.post("/projects/{pid}/report/refine/{node_id:path}")
async def refine(pid: str, node_id: str,
                  body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    outline = load_outline(pid)
    if outline is None:
        raise HTTPException(status_code=400, detail="outline not built")
    node = outline.find(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"node {node_id} not found")
    terms = load_terminology(pid)
    base_ctx = WriterContext(project_id=pid, terminology=terms,
                              extra_instructions=str(body.get("extra_instructions") or ""))
    await publish(pid, "plan.refine_start", {"node_id": node_id})
    try:
        draft = await refine_to_draft(pid, node, base_ctx=base_ctx)
    except Exception as e:  # noqa: BLE001
        await publish(pid, "plan.refine_error", {"node_id": node_id, "error": str(e)[:200]})
        raise HTTPException(status_code=500, detail=f"refine_to_draft failed: {e}")
    await publish(pid, "plan.refine_done", {
        "node_id": node_id, "words": draft.word_count,
        "tokens_in": draft.llm_meta.tokens_in,
        "tokens_out": draft.llm_meta.tokens_out,
    })
    return draft.model_dump()
