"""FastAPI auth dependency — JWT Bearer + dev_mode fallback.

Resolution order:
    1. Authorization: Bearer <jwt>   — preferred, modern client path.
    2. X-User-Id: <uid>              — legacy / dev path; honoured only
                                        when settings.auth.dev_mode is True
                                        (defaults to True so M2-M20 e2e
                                        scripts keep passing).
    3. No headers + dev_mode         — synthesize the dev seed user
                                        'demo_author' so the UI's bare
                                        unauthenticated requests work in
                                        local-only deployments.

Returns a :class:`app.auth.models.User`. On hard failure raises 401.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import HTTPException, Request

from app.auth.jwt_token import decode_token
from app.auth.models import (
    PermissionAction,
    ProjectMember,
    User,
    get_member,
    get_user_by_id,
    upsert_user,
)
from app.config import settings

logger = logging.getLogger("autocsr.auth.middleware")

_DEV_SEED_FALLBACK_ID = "demo_author"


def _dev_mode_enabled() -> bool:
    return bool((settings().get("auth") or {}).get("dev_mode", True))


def _ensure_dev_seed_user(uid: str) -> User:
    """When dev_mode falls back to X-User-Id but the user isn't in the
    store yet (e.g. ad-hoc test header), synthesize a minimal record so
    downstream code can still touch its ``tenant_id``."""
    u = get_user_by_id(uid)
    if u is not None:
        return u
    u = User(
        id=uid,
        email=f"{uid}@dev.local",
        display_name=uid,
        role="user",
        tenant_id="default",
        password_hash="",
        name=uid,
    )
    upsert_user(u)
    return u


def get_current_user(request: Request) -> User:
    """FastAPI dependency."""
    # 1) Bearer JWT --------------------------------------------------------
    auth = request.headers.get("Authorization") or request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            claims = decode_token(token)
        except ValueError as e:
            raise HTTPException(status_code=401, detail=f"invalid token: {e}")
        if claims.get("typ") != "access":
            raise HTTPException(status_code=401, detail="not an access token")
        uid = str(claims.get("sub") or "")
        if not uid:
            raise HTTPException(status_code=401, detail="missing subject")
        user = get_user_by_id(uid)
        if user is None:
            raise HTTPException(status_code=401, detail="user not found")
        # Trust the token's tenant_id over the stored one so token-rotation
        # after a tenant move stays consistent.
        token_tid = str(claims.get("tid") or user.tenant_id)
        if token_tid and token_tid != user.tenant_id:
            user = user.model_copy(update={"tenant_id": token_tid})
        return user
    # 2) X-User-Id dev fallback --------------------------------------------
    if _dev_mode_enabled():
        uid = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
        if uid:
            return _ensure_dev_seed_user(uid)
        # 3) no headers at all → default dev_author so anonymous works.
        return _ensure_dev_seed_user(_DEV_SEED_FALLBACK_ID)
    # No fallback when dev_mode is off → 401.
    raise HTTPException(status_code=401, detail="authentication required")


def get_optional_user(request: Request) -> User | None:
    try:
        return get_current_user(request)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

_ACTION_ALLOWED: dict[str, tuple[PermissionAction, ...]] = {
    "owner": ("read", "write", "comment", "sign", "export", "manage_members", "delete"),
    "editor": ("read", "write", "comment", "export"),
    "reviewer": ("read", "comment", "sign", "export"),
    "viewer": ("read", "export"),
}


def check_permission(user: User, project_owner_tenant_id: str,
                      project_id: str, action: PermissionAction) -> bool:
    """Return True if ``user`` may perform ``action`` on ``project_id``.

    Rules:
        * Different tenant  → always False (tenant isolation hard wall).
        * Same tenant, admin → always True.
        * Same tenant, no member record → read-only.
        * Same tenant, has member record → role-action matrix.
    """
    if user.tenant_id != project_owner_tenant_id:
        return False
    if user.role == "admin":
        return True
    member = get_member(project_owner_tenant_id, project_id, user.id)
    if member is None:
        # Same-tenant non-members default to read so casual browsing works
        # (cross-team visibility); write / comment / sign require explicit grant.
        return action == "read"
    allowed = _ACTION_ALLOWED.get(member.role, ())
    return action in allowed


def ensure_permission(user: User, project_owner_tenant_id: str,
                       project_id: str, action: PermissionAction) -> None:
    if not check_permission(user, project_owner_tenant_id, project_id, action):
        raise HTTPException(status_code=403,
                            detail=f"permission denied: {action} on project {project_id}")
