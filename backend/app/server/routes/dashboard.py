"""M21 — interactive dashboard CRUD."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.analysis.advanced.dashboard import (
    build_dashboard,
    delete_dashboard,
    list_dashboards,
)
from app.auth.middleware import get_current_user
from app.auth.models import User
from app.projects.manager import ensure_project_access

logger = logging.getLogger("autocsr.dashboard.routes")
router = APIRouter(tags=["analysis"])


@router.get("/projects/{pid}/dashboards")
def list_dashboards_endpoint(pid: str,
                              user: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    ensure_project_access(user, pid, "read")
    return [json.loads(d.model_dump_json()) for d in list_dashboards(pid)]


@router.post("/projects/{pid}/dashboard", status_code=201)
def create_dashboard(pid: str, body: dict = Body(...),
                      user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    layout = body.get("layout") or []
    if not isinstance(layout, list):
        raise HTTPException(status_code=400, detail="layout must be a list")
    name = str(body.get("name") or "Untitled")
    dash = build_dashboard(pid, name, layout)
    return json.loads(dash.model_dump_json())


@router.delete("/projects/{pid}/dashboard/{dash_id}")
def delete_dashboard_endpoint(pid: str, dash_id: str,
                               user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    ok = delete_dashboard(pid, dash_id)
    return {"ok": ok}
