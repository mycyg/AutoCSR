"""Sequential signature chain on ReviewTasks (M17).

A *sign chain* is an ordered list of roles that must each electronically
sign a review task in turn (e.g. statistician → medical → regulatory →
approver). The chain is attached to the task as
``ReviewTask.sign_chain`` (see :mod:`app.collab.tasks`).

API surface:

* :func:`init_chain`         — create a default or custom chain
* :func:`advance_chain`      — sign the next pending step
* :func:`get_chain`          — read the current state
* :class:`OutOfOrderError`   — raised when callers try to skip a step

Each successful advance invokes :func:`app.audit.signature.sign` with
``artifact_type='review_task'`` so the e-sig + audit chain capture the
event automatically.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.collab.tasks import ReviewTask, _path as tasks_path
from app.config import data_dir


DEFAULT_STANDARD_CHAIN: list[str] = [
    "statistician", "medical", "regulatory", "approver",
]

SignChainStatus = Literal["pending", "signed", "rejected"]


class OutOfOrderError(RuntimeError):
    """Raised when a caller tries to sign a step before its predecessor."""


class SignChainStep(BaseModel):
    role: str
    signer_user_id: str | None = None
    signed_at: datetime | None = None
    signature_id: str | None = None
    status: SignChainStatus = "pending"
    reason: str | None = None


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


def _read_all(pid: str) -> dict[str, ReviewTask]:
    p = tasks_path(pid)
    if not p.exists():
        return {}
    out: dict[str, ReviewTask] = {}
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = ReviewTask.model_validate_json(line)
            except Exception:
                continue
            out[t.id] = t
    return out


def _append(pid: str, task: ReviewTask) -> None:
    with tasks_path(pid).open("a", encoding="utf-8") as f:
        f.write(task.model_dump_json() + "\n")


def _publish(pid: str, event: str, payload: dict) -> None:
    try:
        from app.server.ws import publish_sync
        publish_sync(pid, event, payload)
    except Exception:
        pass


def init_chain(
    pid: str,
    tid: str,
    *,
    chain: list[str] | None = None,
) -> ReviewTask:
    """Attach a sign-chain to the task.

    If ``chain`` is None we use :data:`DEFAULT_STANDARD_CHAIN`. Calling
    on a task that already has a non-empty chain raises ValueError.
    """
    roles = list(chain) if chain else list(DEFAULT_STANDARD_CHAIN)
    if not roles:
        raise ValueError("chain must contain at least one role")
    with _plock(pid):
        all_tasks = _read_all(pid)
        task = all_tasks.get(tid)
        if task is None:
            raise KeyError(f"task {tid} not found in project {pid}")
        if task.sign_chain:
            raise ValueError("sign_chain already initialised for this task")
        steps = [SignChainStep(role=r).model_dump() for r in roles]
        updated = task.model_copy(update={
            "sign_chain": steps,
            "updated_at": _now(),
        })
        _append(pid, updated)
    _publish(pid, "sign_chain.initialized", {
        "task_id": tid, "roles": roles,
    })
    return updated


def get_chain(pid: str, tid: str) -> list[SignChainStep] | None:
    task = _read_all(pid).get(tid)
    if task is None:
        return None
    return [SignChainStep.model_validate(s) for s in (task.sign_chain or [])]


def advance_chain(
    pid: str,
    tid: str,
    *,
    role: str,
    signer_user_id: str,
    reason: str = "",
) -> SignChainStep:
    """Mark the next pending step as ``signed`` (or raise OutOfOrderError).

    Constraints:

    * the next ``pending`` step in the chain must match ``role``;
    * any earlier step that is still ``pending`` triggers
      :class:`OutOfOrderError`.

    On success we call :func:`app.audit.signature.sign`. If the signing
    backend is unavailable we still mark the step ``signed`` but leave
    ``signature_id`` empty and the failure is reported via the WS bus.
    """
    if not role:
        raise ValueError("role required")
    if not signer_user_id:
        raise ValueError("signer_user_id required")
    with _plock(pid):
        all_tasks = _read_all(pid)
        task = all_tasks.get(tid)
        if task is None:
            raise KeyError(f"task {tid} not found in project {pid}")
        chain_dicts = list(task.sign_chain or [])
        if not chain_dicts:
            raise ValueError("sign_chain not initialised; POST .../sign_chain/init first")
        chain = [SignChainStep.model_validate(s) for s in chain_dicts]
        # Find first pending step
        next_idx = None
        for i, step in enumerate(chain):
            if step.status == "pending":
                next_idx = i
                break
        if next_idx is None:
            raise OutOfOrderError("chain already complete; no pending step")
        expected = chain[next_idx]
        if expected.role != role:
            raise OutOfOrderError(
                f"out-of-order sign attempt: expected role={expected.role!r} "
                f"but caller provided role={role!r}",
            )

        # Try to anchor the signature in the audit / e-sig store
        sig_id: str | None = None
        try:
            from app.audit.signature import sign
            sig = sign(pid, "review_task", tid, signer_user_id,
                       reason=reason or f"sign_chain:{role}")
            sig_id = sig.id
        except Exception as e:  # noqa: BLE001
            _publish(pid, "sign_chain.sign_backend_error", {
                "task_id": tid, "role": role, "error": str(e),
            })

        signed_step = expected.model_copy(update={
            "signer_user_id": signer_user_id,
            "signed_at": _now(),
            "signature_id": sig_id,
            "status": "signed",
            "reason": reason or None,
        })
        chain[next_idx] = signed_step
        updated = task.model_copy(update={
            "sign_chain": [s.model_dump() for s in chain],
            "updated_at": _now(),
        })
        _append(pid, updated)

    _publish(pid, "sign_chain.advanced", {
        "task_id": tid, "role": role,
        "step_index": next_idx,
        "signature_id": sig_id,
        "remaining": sum(1 for s in chain if s.status == "pending"),
    })
    return signed_step


def chain_summary(pid: str, tid: str) -> dict | None:
    """Compact serialisable view used by the docx_builder cover."""
    chain = get_chain(pid, tid)
    if chain is None:
        return None
    return {
        "task_id": tid,
        "total": len(chain),
        "signed": sum(1 for s in chain if s.status == "signed"),
        "pending": sum(1 for s in chain if s.status == "pending"),
        "steps": [
            {
                "role": s.role,
                "status": s.status,
                "signer_user_id": s.signer_user_id,
                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                "signature_id": s.signature_id,
            }
            for s in chain
        ],
    }


__all__ = [
    "DEFAULT_STANDARD_CHAIN", "SignChainStep", "OutOfOrderError",
    "init_chain", "advance_chain", "get_chain", "chain_summary",
]
