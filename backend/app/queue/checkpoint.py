"""Resume-from-checkpoint helper (M17).

Long-running jobs (report generation, cleansing apply) record their
progress to ``data/projects/<pid>/checkpoints/<task_id>.json`` after
every completed item. On restart the orchestrator can call
:func:`resume_from_checkpoint` to skip items already done.

The Checkpoint schema is intentionally compact — the source of truth
for the work payload lives in the orchestrator; we only persist
*which items have been completed* + parameters needed to rebuild the
remaining queue.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "checkpoints"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(pid: str, task_id: str) -> Path:
    safe = task_id.replace("/", "_")
    return _dir(pid) / f"{safe}.json"


class Checkpoint(BaseModel):
    task_id: str
    project_id: str
    kind: str = ""                        # "report.generate" / "cleansing.apply" / ...
    completed_items: list[str] = Field(default_factory=list)
    total: int = 0
    params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    status: str = "running"               # "running" | "done" | "error"
    last_error: str | None = None


def write_checkpoint(
    pid: str,
    task_id: str,
    *,
    kind: str = "",
    completed_items: list[str] | None = None,
    total: int = 0,
    params: dict[str, Any] | None = None,
    status: str = "running",
    last_error: str | None = None,
) -> Checkpoint:
    """Idempotent upsert. Reads any prior checkpoint to preserve
    ``created_at`` and merge ``completed_items`` deterministically."""
    completed_items = list(completed_items or [])
    with _plock(pid):
        prior = load_checkpoint(pid, task_id)
        created = prior.created_at if prior else _now()
        merged = list(dict.fromkeys((prior.completed_items if prior else []) + completed_items))
        cp = Checkpoint(
            task_id=task_id,
            project_id=pid,
            kind=kind or (prior.kind if prior else ""),
            completed_items=merged,
            total=max(total, prior.total if prior else 0),
            params=params if params is not None else (prior.params if prior else {}),
            created_at=created,
            updated_at=_now(),
            status=status,
            last_error=last_error,
        )
        _path(pid, task_id).write_text(
            json.dumps(json.loads(cp.model_dump_json()),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return cp


def record_progress(
    pid: str,
    task_id: str,
    item_id: str,
    *,
    kind: str = "",
    total: int = 0,
    params: dict[str, Any] | None = None,
) -> Checkpoint:
    """Append one completed item id; thin wrapper around write_checkpoint."""
    return write_checkpoint(
        pid, task_id, kind=kind,
        completed_items=[item_id],
        total=total, params=params,
    )


def load_checkpoint(pid: str, task_id: str) -> Checkpoint | None:
    p = _path(pid, task_id)
    if not p.exists():
        return None
    try:
        return Checkpoint.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_checkpoints(pid: str) -> list[Checkpoint]:
    out: list[Checkpoint] = []
    for f in sorted(_dir(pid).glob("*.json")):
        try:
            out.append(Checkpoint.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def delete_checkpoint(pid: str, task_id: str) -> bool:
    p = _path(pid, task_id)
    if p.exists():
        p.unlink()
        return True
    return False


def resume_from_checkpoint(pid: str, task_id: str) -> bool:
    """Return True iff a resumable checkpoint exists."""
    cp = load_checkpoint(pid, task_id)
    return bool(cp and cp.status == "running" and cp.completed_items)


def remaining_items(
    pid: str,
    task_id: str,
    candidate_items: list[str],
) -> list[str]:
    """Filter ``candidate_items`` down to those not yet done."""
    cp = load_checkpoint(pid, task_id)
    if cp is None:
        return list(candidate_items)
    done = set(cp.completed_items)
    return [item for item in candidate_items if item not in done]


def mark_done(pid: str, task_id: str) -> Checkpoint | None:
    """Mark the checkpoint complete (terminal state)."""
    return write_checkpoint(pid, task_id, status="done")


def mark_error(pid: str, task_id: str, error: str) -> Checkpoint | None:
    return write_checkpoint(pid, task_id, status="error", last_error=error)


__all__ = [
    "Checkpoint", "write_checkpoint", "record_progress",
    "load_checkpoint", "list_checkpoints", "delete_checkpoint",
    "resume_from_checkpoint", "remaining_items",
    "mark_done", "mark_error",
]
