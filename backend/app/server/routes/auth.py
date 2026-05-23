"""M21 — authentication & account management routes.

Endpoints (all mounted under /api):
    POST /auth/register
    POST /auth/login
    POST /auth/refresh
    POST /auth/logout
    GET  /auth/me
    PATCH /auth/me

All endpoints are tolerant of dev_mode so unit / e2e tests can hit them
without hard-coded JWT plumbing.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.auth.jwt_token import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.auth.middleware import get_current_user
from app.auth.models import (
    Tenant,
    User,
    ensure_default_tenant,
    get_tenant,
    get_user_by_email,
    get_user_by_id,
    new_tenant_id,
    new_user_id,
    upsert_tenant,
    upsert_user,
)
from app.auth.password import hash_password, verify_password
from app.config import data_dir

logger = logging.getLogger("autocsr.auth.routes")
router = APIRouter(tags=["auth"])


def _blocklist_path() -> Path:
    p = data_dir() / "auth"
    p.mkdir(parents=True, exist_ok=True)
    return p / "blocklist.jsonl"


def _add_to_blocklist(token_jti: str, reason: str = "logout") -> None:
    rec = {"token": token_jti[-16:], "ts": datetime.now(timezone.utc).isoformat(), "reason": reason}
    with _blocklist_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name or u.name,
        "role": u.role,
        "tenant_id": u.tenant_id,
        "created_at": u.created_at.isoformat() if isinstance(u.created_at, datetime) else u.created_at,
        "last_login_at": u.last_login_at.isoformat() if isinstance(u.last_login_at, datetime) else u.last_login_at,
    }


def _tenant_to_dict(t: Tenant) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "plan": t.plan,
        "created_at": t.created_at.isoformat() if isinstance(t.created_at, datetime) else t.created_at,
        "settings": t.settings,
    }


# ---------------------------------------------------------------------------
# /auth/register
# ---------------------------------------------------------------------------


@router.post("/auth/register", status_code=201)
def register(body: dict = Body(...)) -> dict[str, Any]:
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    display_name = str(body.get("display_name") or "").strip()
    tenant_name = str(body.get("tenant_name") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="valid email required")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="password must be at least 6 chars")
    if get_user_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="email already registered")
    if tenant_name:
        tenant = Tenant(id=new_tenant_id(), name=tenant_name, plan="free")
        upsert_tenant(tenant)
    else:
        tenant = ensure_default_tenant()
    uid = new_user_id()
    is_first_user_in_tenant = True  # creator of a fresh tenant is admin
    try:
        from app.auth.models import load_users
        same_tenant = [u for u in load_users() if u.tenant_id == tenant.id]
        is_first_user_in_tenant = len(same_tenant) == 0
    except Exception:
        pass
    user = User(
        id=uid,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or email.split("@", 1)[0],
        role="admin" if is_first_user_in_tenant else "user",
        tenant_id=tenant.id,
        created_at=datetime.now(timezone.utc),
        name=display_name or email.split("@", 1)[0],
    )
    upsert_user(user)
    access = create_access_token(user.id, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)
    return {
        "user": _user_to_dict(user),
        "tenant": _tenant_to_dict(tenant),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
    }


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


@router.post("/auth/login")
def login(body: dict = Body(...)) -> dict[str, Any]:
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    user = get_user_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    # Touch last_login_at.
    user = user.model_copy(update={"last_login_at": datetime.now(timezone.utc)})
    upsert_user(user)
    tenant = get_tenant(user.tenant_id) or ensure_default_tenant()
    access = create_access_token(user.id, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)
    return {
        "user": _user_to_dict(user),
        "tenant": _tenant_to_dict(tenant),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
    }


# ---------------------------------------------------------------------------
# /auth/refresh
# ---------------------------------------------------------------------------


@router.post("/auth/refresh")
def refresh_token(body: dict = Body(...)) -> dict[str, Any]:
    rt = str(body.get("refresh_token") or "")
    if not rt:
        raise HTTPException(status_code=400, detail="refresh_token required")
    try:
        claims = decode_token(rt)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if claims.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="not a refresh token")
    uid = str(claims.get("sub") or "")
    tid = str(claims.get("tid") or "")
    user = get_user_by_id(uid)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    access = create_access_token(user.id, tid or user.tenant_id)
    return {"access_token": access, "token_type": "Bearer"}


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


@router.post("/auth/logout")
def logout(body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    rt = str(body.get("refresh_token") or "")
    if rt:
        _add_to_blocklist(rt)
    return {"ok": True}


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------


@router.get("/auth/me")
def get_me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    tenant = get_tenant(user.tenant_id) or ensure_default_tenant()
    return {"user": _user_to_dict(user), "tenant": _tenant_to_dict(tenant)}


@router.patch("/auth/me")
def update_me(body: dict = Body(...),
              user: User = Depends(get_current_user)) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if "display_name" in body and body["display_name"] is not None:
        dn = str(body["display_name"]).strip()
        if not dn:
            raise HTTPException(status_code=400, detail="display_name cannot be empty")
        patch["display_name"] = dn
        patch["name"] = dn
    if "password" in body and body["password"]:
        pwd = str(body["password"])
        if len(pwd) < 6:
            raise HTTPException(status_code=400, detail="password must be at least 6 chars")
        patch["password_hash"] = hash_password(pwd)
    if not patch:
        return _user_to_dict(user)
    updated = user.model_copy(update=patch)
    upsert_user(updated)
    return _user_to_dict(updated)
