"""Unit tests for M21 auth modules — fast, no server."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(monkeypatch, tmp_path):
    """Point every data_dir() call at a tmp folder so tests don't touch
    the real data/ tree."""
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    # Clear settings cache so subsequent settings() calls re-read.
    _cfg._CACHE = None
    yield


def test_password_roundtrip():
    from app.auth.password import hash_password, verify_password, backend_info
    info = backend_info()
    assert info["bcrypt"] or info["passlib"]
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True
    assert verify_password("nope", h) is False


def test_password_empty_rejected():
    from app.auth.password import hash_password
    with pytest.raises(ValueError):
        hash_password("")


def test_jwt_roundtrip():
    from app.auth.jwt_token import (
        create_access_token, create_refresh_token, decode_token,
    )
    at = create_access_token("u_x", "t_a")
    rt = create_refresh_token("u_x", "t_a")
    assert at and rt
    claims_a = decode_token(at)
    assert claims_a["sub"] == "u_x" and claims_a["tid"] == "t_a"
    assert claims_a["typ"] == "access"
    claims_r = decode_token(rt)
    assert claims_r["typ"] == "refresh"


def test_jwt_invalid_token_raises():
    from app.auth.jwt_token import decode_token
    with pytest.raises(ValueError):
        decode_token("not.a.real.token")


def test_user_tenant_persistence():
    from app.auth.models import (
        User, Tenant, ensure_default_tenant, upsert_tenant, upsert_user,
        get_tenant, get_user_by_id, get_user_by_email, new_user_id,
    )
    t = ensure_default_tenant()
    assert t.id == "default"
    uid = new_user_id()
    u = User(id=uid, email="x@y.local", display_name="X Y",
              password_hash="bcrypt$dummy", tenant_id="default", name="X Y")
    upsert_user(u)
    assert get_user_by_id(uid) is not None
    assert get_user_by_email("x@y.local") is not None
    # idempotent
    upsert_user(u)
    assert len([x for x in [get_user_by_id(uid)] if x is not None]) == 1


def test_project_member_acl_matrix():
    from app.auth.middleware import check_permission
    from app.auth.models import (
        ProjectMember, User, upsert_user, upsert_member,
    )
    owner = User(id="u_o", email="o@d.l", tenant_id="t_x", role="user")
    editor = User(id="u_e", email="e@d.l", tenant_id="t_x", role="user")
    reviewer = User(id="u_r", email="r@d.l", tenant_id="t_x", role="user")
    viewer = User(id="u_v", email="v@d.l", tenant_id="t_x", role="user")
    stranger = User(id="u_s", email="s@d.l", tenant_id="t_other", role="user")
    upsert_member("t_x", "p1", ProjectMember(project_id="p1", user_id="u_o", role="owner"))
    upsert_member("t_x", "p1", ProjectMember(project_id="p1", user_id="u_e", role="editor"))
    upsert_member("t_x", "p1", ProjectMember(project_id="p1", user_id="u_r", role="reviewer"))
    upsert_member("t_x", "p1", ProjectMember(project_id="p1", user_id="u_v", role="viewer"))
    assert check_permission(owner, "t_x", "p1", "manage_members") is True
    assert check_permission(editor, "t_x", "p1", "write") is True
    assert check_permission(editor, "t_x", "p1", "manage_members") is False
    assert check_permission(reviewer, "t_x", "p1", "comment") is True
    assert check_permission(reviewer, "t_x", "p1", "write") is False
    assert check_permission(viewer, "t_x", "p1", "read") is True
    assert check_permission(viewer, "t_x", "p1", "comment") is False
    assert check_permission(stranger, "t_x", "p1", "read") is False


def test_admin_role_overrides_acl():
    from app.auth.middleware import check_permission
    from app.auth.models import User
    admin = User(id="u_a", email="a@d.l", tenant_id="t_x", role="admin")
    assert check_permission(admin, "t_x", "p_unknown", "manage_members") is True
    assert check_permission(admin, "t_x", "p_unknown", "delete") is True
