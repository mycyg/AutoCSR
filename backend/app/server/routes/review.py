"""Reviewer agent routes (M10)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.reviewer_agent import (
    load_history, load_latest, patch_issue, run_review,
)
from app.config import data_dir

logger = logging.getLogger("autocsr.routes.review")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/review")
async def start_review(pid: str,
                        body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    sync = bool(body.get("sync", True))
    if not sync:
        # Fire-and-forget — return immediately, frontend follows WS
        asyncio.create_task(run_review(pid))
        return {"started": True}
    result = await run_review(pid)
    return result.model_dump()


@router.get("/projects/{pid}/review")
def get_latest(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    latest = load_latest(pid)
    if latest is None:
        # Return empty stub for first-time projects so the UI can render
        return {"project_id": pid, "passed": False, "issues": [],
                "checkers": [], "created_at": None, "ignored_issue_ids": []}
    return latest.model_dump()


@router.get("/projects/{pid}/review/history")
def get_history(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [h.model_dump() for h in load_history(pid)]


@router.patch("/projects/{pid}/review/issues/{issue_id}")
def update_issue(pid: str, issue_id: str,
                   body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    ignored = bool(body.get("ignored", True))
    ok = patch_issue(pid, issue_id, ignored=ignored)
    if not ok:
        raise HTTPException(status_code=404, detail=f"issue {issue_id} not found")
    latest = load_latest(pid)
    return latest.model_dump() if latest else {"ok": True}
