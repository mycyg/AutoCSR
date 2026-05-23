"""M21 — project ↔ tenant resolution + permission helpers.

Pre-M21 the entire codebase stored project artefacts at
``data/projects/<pid>/...``. M21 introduces the tenant concept but
keeps that disk layout intact to avoid touching 60+ existing modules.
Instead we expose:

    * project_record(pid) — load a single project row from projects.json
    * project_dir(pid)    — the physical artefact directory (unchanged)
    * project_tenant(pid) — resolves the tenant_id for the given project,
                              defaulting to 'default' for legacy records.

Multi-tenant enforcement happens at the route layer through
``ensure_project_access`` which short-circuits with 403 if the current
user belongs to a different tenant or lacks the project-level role for
the requested action.

The physical file layout is left at the M20 location so the entire
state, audit, sign-chain, corpus, analysis, export and queue subsystems
keep working without modification. A future v3 milestone may migrate
the artefact directories to ``data/tenants/<tid>/projects/<pid>/`` once
the per-module rewrites are scheduled — the migration script in
``scripts/migrate_to_multitenant.py`` already pre-creates that path so
the move can be done with a single shutil.move in a follow-up.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.auth.middleware import ensure_permission
from app.auth.models import (
    PermissionAction,
    ProjectMember,
    User,
    list_members,
    upsert_member,
)
from app.config import data_dir

logger = logging.getLogger("autocsr.projects.manager")

_LOCK = threading.RLock()


def _projects_json() -> Path:
    return data_dir() / "projects.json"


def project_dir(pid: str, tenant_id: str | None = None) -> Path:  # noqa: ARG001
    """Resolve the physical project directory.

    ``tenant_id`` is accepted (and recorded in audit logs) but ignored at
    storage resolution time so the legacy disk layout keeps working.
    """
    return data_dir() / "projects" / pid


def list_all_projects() -> list[dict[str, Any]]:
    p = _projects_json()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except json.JSONDecodeError:
        return []


def project_record(pid: str) -> dict[str, Any] | None:
    for it in list_all_projects():
        if it.get("id") == pid:
            return it
    return None


def project_tenant(pid: str) -> str:
    rec = project_record(pid)
    if rec is None:
        return "default"
    return str(rec.get("tenant_id") or "default")


def write_project_tenant(pid: str, tenant_id: str) -> None:
    """Stamp tenant_id onto an existing project record. Idempotent."""
    with _LOCK:
        p = _projects_json()
        if not p.exists():
            return
        items = list_all_projects()
        changed = False
        for it in items:
            if it.get("id") == pid:
                if it.get("tenant_id") != tenant_id:
                    it["tenant_id"] = tenant_id
                    changed = True
                break
        if changed:
            p.write_text(json.dumps(items, ensure_ascii=False, indent=2, default=str),
                          encoding="utf-8")


def ensure_owner_member(pid: str, tenant_id: str, user_id: str) -> ProjectMember:
    """Make sure the creator of a project is recorded as its owner."""
    return upsert_member(tenant_id, pid, ProjectMember(
        project_id=pid, user_id=user_id, role="owner", granted_by=user_id,
    ))


def ensure_project_access(user: User, pid: str,
                            action: PermissionAction = "read") -> dict[str, Any]:
    """Single guard used by all /api/projects/{pid}/... routes.

    Returns the project record so callers can avoid the second lookup.
    """
    rec = project_record(pid)
    if rec is None:
        # Treat missing record as 404 (no info leak about other tenants).
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    tenant_id = str(rec.get("tenant_id") or "default")
    ensure_permission(user, tenant_id, pid, action)
    return rec


def project_members(pid: str) -> list[ProjectMember]:
    tenant_id = project_tenant(pid)
    return list_members(tenant_id, pid)
