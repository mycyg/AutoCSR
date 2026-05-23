"""Database-lock state (M15).

Once locked, all data-mutating routes (cleansing apply / analysis /
section markdown PATCH) refuse to run unless the request carries
``X-Addendum: true``. Locking and unlocking both require a signature.

Storage: ``data/projects/<pid>/lock.json``::

    {"locked": true, "reason": "Database lock", "ts": "...",
     "signature_id": "sig_..."}
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir

_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


def _path(pid: str) -> Path:
    return data_dir() / "projects" / pid / "lock.json"


def get(pid: str) -> dict[str, Any]:
    p = _path(pid)
    if not p.exists():
        return {"locked": False, "reason": "", "ts": None, "signature_id": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"locked": False}
    except json.JSONDecodeError:
        return {"locked": False}


def is_locked(pid: str) -> bool:
    return bool(get(pid).get("locked"))


def set_locked(pid: str, locked: bool, *, reason: str = "",
               signature_id: str | None = None) -> dict[str, Any]:
    with _plock(pid):
        payload = {
            "locked": bool(locked),
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
            "signature_id": signature_id,
        }
        p = _path(pid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    try:
        from app.server.ws import publish_sync
        publish_sync(pid, "state.lock_changed", {
            "locked": payload["locked"], "reason": reason,
            "signature_id": signature_id,
        })
    except Exception:
        pass
    return payload
