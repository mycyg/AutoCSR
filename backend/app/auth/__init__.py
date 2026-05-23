"""M21 (v2.3) — multi-tenant authentication.

Public surface:
    User, Tenant, ProjectMember            (schemas)
    hash_password / verify_password         (bcrypt with passlib fallback)
    create_access_token / create_refresh_token / decode_token
    get_current_user (FastAPI dependency)
    check_permission

Storage layout:
    data/users.json                — global user directory
    data/tenants.json              — global tenant directory
    data/tenants/<tid>/projects/<pid>/members.json   — per-project ACL
    data/auth/blocklist.jsonl      — revoked refresh tokens

Backwards-compat:
    * Pre-M21 dev users in users.json (no password_hash, no tenant_id) are
      transparently upgraded on first read — slotted into the 'default'
      tenant with a deterministic dev_password 'dev'.
    * settings.auth.dev_mode = true keeps the legacy X-User-Id header
      behaviour so the M2-M20 e2e suites pass unchanged.
"""
from __future__ import annotations

from app.auth.models import (
    ProjectMember,
    Tenant,
    User,
    PermissionAction,
)
from app.auth.password import hash_password, verify_password
from app.auth.jwt_token import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.auth.middleware import get_current_user, check_permission

__all__ = [
    "User",
    "Tenant",
    "ProjectMember",
    "PermissionAction",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "check_permission",
]
