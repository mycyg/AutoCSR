"""Dev-mode user directory (M16).

The real SSO / OIDC plumbing is out of scope for V2; this module ships
four seed users so the UI's user-switch + assignment dropdowns have
something to point at. Routes call :func:`ensure_dev_seed` on first
request; it's idempotent.

Storage: ``data/users.json`` (single global file, not per-project).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.config import data_dir, settings

Role = Literal["author", "reviewer", "approver", "admin"]


class User(BaseModel):
    id: str
    name: str
    email: str = ""
    role: Role = "reviewer"


_LOCK = threading.Lock()


def _path() -> Path:
    return data_dir() / "users.json"


def _load() -> list[User]:
    p = _path()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [User.model_validate(u) for u in raw]
    except Exception:
        pass
    return []


def _save(users: list[User]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([u.model_dump() for u in users], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_DEV_SEED: tuple[User, ...] = (
    User(id="demo_author",   name="撰写者 Author Demo",   role="author"),
    User(id="demo_reviewer", name="审稿人 Reviewer Demo", role="reviewer"),
    User(id="demo_approver", name="审批人 Approver Demo", role="approver"),
    User(id="demo_admin",    name="管理员 Admin Demo",    role="admin"),
)


def ensure_dev_seed() -> None:
    seg = settings().get("collab") or {}
    if not bool(seg.get("dev_seed_users", True)):
        return
    with _LOCK:
        existing = _load()
        if existing:
            return
        _save(list(_DEV_SEED))


def list_users() -> list[User]:
    with _LOCK:
        users = _load()
    if not users:
        ensure_dev_seed()
        with _LOCK:
            users = _load()
    return users


def get_user(user_id: str) -> User | None:
    for u in list_users():
        if u.id == user_id:
            return u
    return None
