"""Auth domain models — User, Tenant, ProjectMember.

Persisted as JSON files; tiny enough for the open-source target user
base (single-installation deployments). A future v3 milestone may swap
the store for SQLite without touching the public function signatures.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

from app.config import data_dir

Role = Literal["admin", "user"]
ProjectRole = Literal["owner", "editor", "reviewer", "viewer"]
TenantPlan = Literal["free", "pro", "enterprise"]
PermissionAction = Literal[
    "read", "write", "comment", "sign", "export", "manage_members", "delete"
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(BaseModel):
    id: str
    email: str
    password_hash: str = ""
    display_name: str = ""
    role: Role = "user"
    tenant_id: str = "default"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None
    # Legacy M16 fields — kept so the dev seed users (demo_author / ...) keep
    # rendering in collab assignment dropdowns.
    name: str = ""
    legacy_role: str | None = None


class Tenant(BaseModel):
    id: str
    name: str
    plan: TenantPlan = "free"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectMember(BaseModel):
    project_id: str
    user_id: str
    role: ProjectRole = "viewer"
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    granted_by: str = ""


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()


def _users_path() -> Path:
    return data_dir() / "users.json"


def _tenants_path() -> Path:
    return data_dir() / "tenants.json"


def _members_path(tenant_id: str, project_id: str) -> Path:
    p = data_dir() / "tenants" / tenant_id / "projects" / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p / "members.json"


def _normalize_user_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Back-fill M21 fields for historical / dev-seed user records."""
    out = dict(raw)
    out.setdefault("id", "unknown")
    out.setdefault("email", "")
    out.setdefault("password_hash", "")
    out.setdefault("display_name", out.get("name") or out["id"])
    # Map legacy collab role ('author'/'reviewer'/...) into the M21 role.
    legacy_role = out.get("role")
    if legacy_role in ("admin",):
        m21_role = "admin"
    elif legacy_role in (None, "user", "admin"):
        m21_role = legacy_role or "user"
    else:
        m21_role = "user"
    out["legacy_role"] = legacy_role if legacy_role not in ("admin", "user", None) else out.get("legacy_role")
    out["role"] = m21_role
    out.setdefault("tenant_id", "default")
    out.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    out.setdefault("last_login_at", None)
    out.setdefault("name", out.get("display_name") or out["id"])
    return out


def load_users() -> list[User]:
    p = _users_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [User.model_validate(_normalize_user_dict(u)) for u in raw]
    except Exception:
        return []


def save_users(users: list[User]) -> None:
    p = _users_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([json.loads(u.model_dump_json()) for u in users],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_user_by_id(uid: str) -> User | None:
    return next((u for u in load_users() if u.id == uid), None)


def get_user_by_email(email: str) -> User | None:
    e = email.strip().lower()
    return next((u for u in load_users() if u.email.lower() == e), None)


def upsert_user(user: User) -> User:
    with _LOCK:
        users = load_users()
        for i, u in enumerate(users):
            if u.id == user.id:
                users[i] = user
                break
        else:
            users.append(user)
        save_users(users)
        return user


def load_tenants() -> list[Tenant]:
    p = _tenants_path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [Tenant.model_validate(t) for t in raw]
    except Exception:
        return []


def save_tenants(tenants: list[Tenant]) -> None:
    p = _tenants_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([json.loads(t.model_dump_json()) for t in tenants],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_tenant(tid: str) -> Tenant | None:
    return next((t for t in load_tenants() if t.id == tid), None)


def upsert_tenant(tenant: Tenant) -> Tenant:
    with _LOCK:
        tenants = load_tenants()
        for i, t in enumerate(tenants):
            if t.id == tenant.id:
                tenants[i] = tenant
                break
        else:
            tenants.append(tenant)
        save_tenants(tenants)
        return tenant


def ensure_default_tenant() -> Tenant:
    """Idempotent — used by migration + first-boot."""
    with _LOCK:
        t = get_tenant("default")
        if t is not None:
            return t
        t = Tenant(id="default", name="Default Tenant", plan="free")
        upsert_tenant(t)
        return t


def new_user_id() -> str:
    return "u_" + uuid.uuid4().hex[:12]


def new_tenant_id() -> str:
    return "t_" + uuid.uuid4().hex[:10]


# ---------------------------------------------------------------------------
# Project members
# ---------------------------------------------------------------------------


def list_members(tenant_id: str, project_id: str) -> list[ProjectMember]:
    p = _members_path(tenant_id, project_id)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [ProjectMember.model_validate(m) for m in raw]
    except Exception:
        return []


def save_members(tenant_id: str, project_id: str,
                  members: list[ProjectMember]) -> None:
    p = _members_path(tenant_id, project_id)
    p.write_text(
        json.dumps([json.loads(m.model_dump_json()) for m in members],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_member(tenant_id: str, project_id: str, user_id: str) -> ProjectMember | None:
    return next((m for m in list_members(tenant_id, project_id) if m.user_id == user_id), None)


def upsert_member(tenant_id: str, project_id: str,
                   member: ProjectMember) -> ProjectMember:
    with _LOCK:
        members = list_members(tenant_id, project_id)
        for i, m in enumerate(members):
            if m.user_id == member.user_id:
                members[i] = member
                break
        else:
            members.append(member)
        save_members(tenant_id, project_id, members)
        return member


def remove_member(tenant_id: str, project_id: str, user_id: str) -> bool:
    with _LOCK:
        members = list_members(tenant_id, project_id)
        keep = [m for m in members if m.user_id != user_id]
        if len(keep) == len(members):
            return False
        save_members(tenant_id, project_id, keep)
        return True
