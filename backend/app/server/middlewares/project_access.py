"""Coarse project access guard for legacy project routes.

Many older route modules predate M21 and only check that a project directory
exists. This middleware provides a tenant/role backstop for every
``/api/projects/{pid}/...`` request while route-level dependencies continue to
enforce stricter actions where they already exist.
"""
from __future__ import annotations

import re

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.middleware import get_current_user
from app.auth.models import PermissionAction
from app.config import settings
from app.projects.manager import ensure_project_access

_PID_RE = re.compile(r"^/api/projects/(?P<pid>[^/]+)(?:/|$)")
_SKIP_PSEUDO_PROJECTS = {"from_template", "from_sample"}


def _dev_mode_enabled() -> bool:
    return bool((settings().get("auth") or {}).get("dev_mode", True))


def _action_for(method: str, path: str) -> PermissionAction:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return "read"
    if method == "DELETE":
        return "delete"
    if "/export" in path or "/exports" in path or "/ectd" in path:
        return "export"
    if "/review" in path or "/comments" in path or "/tasks" in path:
        return "comment"
    if "/sign" in path:
        return "sign"
    if "/members" in path:
        return "manage_members"
    return "write"


class ProjectAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path or ""
        m = _PID_RE.match(path)
        if not m:
            return await call_next(request)
        pid = m.group("pid")
        if pid in _SKIP_PSEUDO_PROJECTS:
            return await call_next(request)
        # Dev mode escape hatch: rely on route-level dependencies only.
        # Production deployments set auth.dev_mode=false and get full
        # tenant + ACL enforcement here.
        if _dev_mode_enabled():
            return await call_next(request)
        try:
            user = get_current_user(request)
            ensure_project_access(user, pid, _action_for(request.method, path))
        except HTTPException as exc:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=exc.status_code,
                                content={"detail": exc.detail})
        return await call_next(request)
