"""Users + Tasks routes (M16)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.collab import tasks as tasks_mod
from app.collab.tasks import TaskComment
from app.collab.users import ensure_dev_seed, get_user, list_users
from app.config import data_dir

router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
def get_users() -> list[dict[str, Any]]:
    ensure_dev_seed()
    return [u.model_dump() for u in list_users()]


@router.get("/users/me")
def whoami(request: Request) -> dict[str, Any]:
    uid = request.headers.get("X-User-Id") or "demo_author"
    u = get_user(uid)
    if u is None:
        # Synthesize a phantom record so the UI always renders something
        return {"id": uid, "name": uid, "role": "reviewer", "email": ""}
    return u.model_dump()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/tasks")
def list_tasks(
    pid: str,
    assignee: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    node_id: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [t.model_dump() for t in tasks_mod.list_tasks(
        pid, assignee=assignee, status=status,
        severity=severity, node_id=node_id,
    )]


@router.post("/projects/{pid}/tasks", status_code=201)
def create_task(
    pid: str, request: Request, body: dict = Body(...)
) -> dict[str, Any]:
    _ensure_project(pid)
    assignee = str(body.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee required")
    creator = request.headers.get("X-User-Id") or str(body.get("creator") or "")
    severity = str(body.get("severity") or "warn")
    body_text = str(body.get("body") or "")
    title = str(body.get("title") or "").strip() or body_text[:60]
    node_id = body.get("node_id")
    due_raw = body.get("due_date")
    due_dt = _parse_dt(due_raw) if due_raw else None
    t = tasks_mod.create_task(
        pid, assignee=assignee, creator=creator,
        body=body_text, title=title,
        node_id=node_id, severity=severity,  # type: ignore[arg-type]
        source="manual", due_date=due_dt,
    )
    return t.model_dump()


@router.get("/projects/{pid}/tasks/{tid}")
def get_task(pid: str, tid: str) -> dict[str, Any]:
    _ensure_project(pid)
    t = tasks_mod.get_task(pid, tid)
    if t is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return t.model_dump()


@router.patch("/projects/{pid}/tasks/{tid}")
def patch_task(pid: str, tid: str, request: Request,
               body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    add_comment = None
    if body.get("comment"):
        add_comment = TaskComment(
            id="tc_" + uuid.uuid4().hex[:10],
            author=request.headers.get("X-User-Id") or "anonymous",
            body=str(body["comment"]),
            ts=datetime.now(timezone.utc),
        )
    updated = tasks_mod.patch_task(
        pid, tid,
        status=body.get("status"),
        assignee=body.get("assignee"),
        body=body.get("body"),
        title=body.get("title"),
        severity=body.get("severity"),
        add_comment=add_comment,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return updated.model_dump()


@router.post("/projects/{pid}/tasks/{tid}/assign")
def assign(pid: str, tid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    assignee = str(body.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee required")
    updated = tasks_mod.patch_task(pid, tid, assignee=assignee)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return updated.model_dump()


@router.post("/projects/{pid}/tasks/{tid}/resolve")
def resolve(pid: str, tid: str) -> dict[str, Any]:
    _ensure_project(pid)
    updated = tasks_mod.resolve_task(pid, tid)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return updated.model_dump()


@router.post("/projects/{pid}/tasks/{tid}/reopen")
def reopen(pid: str, tid: str) -> dict[str, Any]:
    _ensure_project(pid)
    updated = tasks_mod.reopen_task(pid, tid)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return updated.model_dump()


@router.delete("/projects/{pid}/tasks/{tid}")
def delete_task(pid: str, tid: str) -> dict[str, Any]:
    _ensure_project(pid)
    ok = tasks_mod.delete_task(pid, tid)
    return {"ok": ok, "id": tid}


# Spawn helpers --------------------------------------------------------------

@router.post("/projects/{pid}/tasks/from_issue/{issue_id}")
def from_issue(pid: str, issue_id: str, request: Request,
               body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    assignee = str(body.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee required")
    creator = request.headers.get("X-User-Id") or str(body.get("creator") or "")
    due_raw = body.get("due_date")
    due_dt = _parse_dt(due_raw) if due_raw else None
    t = tasks_mod.from_issue(
        pid, issue_id, assignee=assignee, creator=creator, due_date=due_dt,
    )
    if t is None:
        raise HTTPException(status_code=404, detail=f"issue {issue_id} not found")
    return t.model_dump()


@router.post("/projects/{pid}/tasks/from_comment/{cid}")
def from_comment(pid: str, cid: str, request: Request,
                 body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    assignee = str(body.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee required")
    creator = request.headers.get("X-User-Id") or str(body.get("creator") or "")
    due_raw = body.get("due_date")
    due_dt = _parse_dt(due_raw) if due_raw else None
    t = tasks_mod.from_comment(
        pid, cid, assignee=assignee, creator=creator, due_date=due_dt,
    )
    if t is None:
        raise HTTPException(status_code=404, detail=f"comment {cid} not found")
    return t.model_dump()


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None
