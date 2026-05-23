"""M16 — parallel 3-expert reviewer + project comparison routes."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.reviewers.multi import load_latest_multi, run_multi_review
from app.config import data_dir
from app.queue import enqueue, get_status
from app.state.diff_projects import diff_projects

router = APIRouter(tags=["review"])


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


# M17 — resume a long-running job from its checkpoint --------------
@router.post("/tasks/{task_id}/resume")
async def task_resume(task_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Inspect the checkpoint and resume if any items remain.

    The body may contain ``project_id`` when the checkpoint scope is
    ambiguous. Otherwise we walk every project on disk to find one.
    """
    body = body or {}
    pid = str(body.get("project_id") or "").strip()
    from app.queue import checkpoint as _cp
    from app.config import data_dir
    cp = None
    if pid:
        cp = _cp.load_checkpoint(pid, task_id)
    else:
        projects_dir = data_dir() / "projects"
        if projects_dir.exists():
            for proj_path in projects_dir.iterdir():
                if not proj_path.is_dir():
                    continue
                maybe = _cp.load_checkpoint(proj_path.name, task_id)
                if maybe is not None:
                    cp = maybe
                    pid = proj_path.name
                    break
    if cp is None:
        raise HTTPException(status_code=404,
                            detail=f"checkpoint not found for task {task_id}")
    remaining = max(0, cp.total - len(cp.completed_items))
    resumed = False
    # We only fire a background resume when the kind is actually
    # report.generate AND we have a running event loop. For other kinds
    # (or when called from a sync context like a unit test), we simply
    # report the checkpoint state.
    if cp.status == "running" and remaining > 0 and cp.kind == "report.generate":
        try:
            import asyncio
            from app.report.orchestrator import write_all
            params = dict(cp.params or {})
            params.pop("only_phases", None)
            async def _bg() -> None:
                try:
                    await write_all(pid, task_id=task_id, **params)
                except Exception as exc:  # noqa: BLE001
                    _cp.mark_error(pid, task_id, f"resume failed: {exc!r}")
            asyncio.get_running_loop().create_task(_bg())
            resumed = True
        except Exception:
            resumed = False
    return {
        "task_id": task_id,
        "project_id": pid,
        "status": cp.status,
        "completed": len(cp.completed_items),
        "total": cp.total,
        "remaining": remaining,
        "resumed": resumed,
    }


# Register queue handler at import time
def _register_queue_handlers() -> None:
    from app.queue.runtime import register_handler

    async def _multi_review_handler(project_id: str) -> dict[str, Any]:
        result = await run_multi_review(project_id)
        return result.model_dump()

    register_handler("multi_review", _multi_review_handler)


_register_queue_handlers()
