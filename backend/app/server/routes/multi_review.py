"""M16 — parallel 3-expert reviewer + project comparison routes."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.reviewers.multi import load_latest_multi, run_multi_review
from app.config import data_dir
from app.queue import enqueue, get_status
from app.state.diff_projects import diff_projects

router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/multi_review")
async def trigger(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    sync = bool(body.get("sync", True))
    if sync:
        result = await run_multi_review(pid)
        return result.model_dump()
    # Async path via queue abstraction
    task_id = enqueue("multi_review", {"project_id": pid}, project_id=pid)
    return {"started": True, "task_id": task_id}


@router.get("/projects/{pid}/multi_review")
def get_latest(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    latest = load_latest_multi(pid)
    if latest is None:
        return {"project_id": pid, "statistician": None, "medical": None,
                "regulatory": None, "combined_count": {}, "created_at": None}
    return latest.model_dump()


# Project comparison ---------------------------------------------------------

@router.post("/projects/compare")
def compare(body: dict = Body(...)) -> dict[str, Any]:
    pid_a = str(body.get("pid_a") or "").strip()
    pid_b = str(body.get("pid_b") or "").strip()
    if not (pid_a and pid_b):
        raise HTTPException(status_code=400, detail="pid_a and pid_b required")
    by = str(body.get("by") or "outline").lower()
    if by not in ("outline", "drafts"):
        raise HTTPException(status_code=400, detail="by must be 'outline' or 'drafts'")
    for p in (pid_a, pid_b):
        if not (data_dir() / "projects" / p).exists():
            raise HTTPException(status_code=404, detail=f"project {p} not found")
    return diff_projects(pid_a, pid_b, by=by).model_dump()


# Task-queue surface ---------------------------------------------------------

@router.get("/tasks/{task_id}/status")
def task_status(task_id: str) -> dict[str, Any]:
    rec = get_status(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"task {task_id} not found")
    from dataclasses import asdict
    return asdict(rec)


@router.post("/tasks/{task_id}/cancel")
def task_cancel(task_id: str) -> dict[str, Any]:
    from app.queue import cancel
    ok = cancel(task_id)
    return {"ok": bool(ok), "id": task_id}


# Register queue handler at import time
def _register_queue_handlers() -> None:
    from app.queue.runtime import register_handler

    async def _multi_review_handler(project_id: str) -> dict[str, Any]:
        result = await run_multi_review(project_id)
        return result.model_dump()

    register_handler("multi_review", _multi_review_handler)


_register_queue_handlers()
