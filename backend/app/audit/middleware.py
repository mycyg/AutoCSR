"""FastAPI middleware that auto-appends an :class:`AuditEvent` for every
mutation that targets a per-project resource (M15).

A mutation is any POST / PATCH / PUT / DELETE whose path contains
``/projects/{pid}/``. GET requests are not audited (they would dwarf the
log without adding integrity value). The middleware runs after the route
returns so it knows the HTTP status; failures still get recorded.
"""
from __future__ import annotations

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.audit.trail import append_event, make_event

logger = logging.getLogger("autocsr.audit.middleware")

# Capture project id from any path like ``/api/projects/<id>/<rest...>``
_PID_RE = re.compile(r"/projects/(?P<pid>[A-Za-z0-9_\-]{4,})(?:/|$)")

_MUTATION_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# Routes whose payloads are too noisy for the audit log (per-request
# polling, websocket-style endpoints). Suffix match against the path.
_SKIP_SUFFIXES = (
    "/state",                     # heartbeats
    "/state_summary",
    "/cleansing/diff",            # read-shaped POST
    "/cleansing/proposals",       # noisy; the apply call is what matters
)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            if request.method not in _MUTATION_METHODS:
                return response
            path = request.url.path or ""
            m = _PID_RE.search(path)
            if not m:
                return response
            if any(path.endswith(s) for s in _SKIP_SUFFIXES):
                return response
            pid = m.group("pid")
            actor = request.headers.get("X-User-Id") or "anonymous"
            ip = request.client.host if request.client else None
            # Best-effort resource_type heuristic
            resource_type = _resource_type_from_path(path)
            event = make_event(
                actor=actor,
                action=f"{request.method} {path}",
                resource_type=resource_type,
                resource_id="",
                reason=request.headers.get("X-Audit-Reason"),
                ip=ip,
                extra={
                    "status_code": response.status_code,
                },
            )
            append_event(pid, event)
        except Exception as e:  # noqa: BLE001
            logger.warning("audit middleware failed: %s", e)
        return response


def _resource_type_from_path(path: str) -> str:
    # /api/projects/<pid>/<segment>/...
    parts = [p for p in path.split("/") if p]
    try:
        i = parts.index("projects")
        segment = parts[i + 2] if i + 2 < len(parts) else "project"
    except ValueError:
        return "unknown"
    # Normalize common ones
    mapping = {
        "cleansing": "cleansing",
        "ingest": "ingestion",
        "analysis": "analysis",
        "outline": "outline",
        "report": "report",
        "chat": "chat",
        "export": "export",
        "review": "review",
        "comments": "comment",
        "markers": "marker",
        "tasks": "task",
        "sign": "signature",
        "state": "state",
        "import_csr": "import_csr",
    }
    return mapping.get(segment, segment or "unknown")


def install(app: ASGIApp) -> None:
    """Convenience hook to mount this middleware on a FastAPI app."""
    app.add_middleware(AuditMiddleware)  # type: ignore[arg-type]
