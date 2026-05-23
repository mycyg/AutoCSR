"""Blinding + database-lock + safety helper routes (M15)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from app.audit import load_signature, verify as verify_sig
from app.config import data_dir
from app.state import blinding as _blinding
from app.state import lock as _lock

router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/state/blinding")
def get_blinding(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    return _blinding.get(pid)


@router.patch("/projects/{pid}/state/blinding")
def patch_blinding(pid: str, request: Request,
                   body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    target = bool(body.get("blinded"))
    signature_id = body.get("signature_id") or request.headers.get("X-Signature-Id")
    cur = _blinding.get(pid)
    # Unblinding (True -> False) requires a verified signature
    if cur.get("blinded") and not target:
        if not signature_id:
            raise HTTPException(
                status_code=403,
                detail="unblinding requires a signature_id (sign blinding_change first)",
            )
        sig = load_signature(pid, str(signature_id))
        if sig is None or not verify_sig(pid, str(signature_id)):
            raise HTTPException(
                status_code=403,
                detail="signature_id invalid or unverifiable",
            )
    arms = body.get("arms")
    if arms is not None and not isinstance(arms, list):
        raise HTTPException(status_code=400, detail="arms must be a list of strings")
    return _blinding.set_blinded(
        pid, target,
        signature_id=str(signature_id) if signature_id else None,
        arms=arms,
    )


# ---------------------------------------------------------------------------
# Database lock
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/state/lock")
def get_lock(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    return _lock.get(pid)


@router.post("/projects/{pid}/state/lock")
def post_lock(pid: str, request: Request,
              body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    reason = str(body.get("reason") or "")
    signature_id = body.get("signature_id") or request.headers.get("X-Signature-Id")
    if not signature_id:
        raise HTTPException(
            status_code=403,
            detail="locking requires a signature_id",
        )
    sig = load_signature(pid, str(signature_id))
    if sig is None or not verify_sig(pid, str(signature_id)):
        raise HTTPException(
            status_code=403,
            detail="signature_id invalid or unverifiable",
        )
    return _lock.set_locked(pid, True, reason=reason,
                            signature_id=str(signature_id))


@router.delete("/projects/{pid}/state/lock")
def delete_lock(pid: str, request: Request) -> dict[str, Any]:
    """Unlock the database — same signature gate as lock."""
    _ensure_project(pid)
    signature_id = request.headers.get("X-Signature-Id")
    if not signature_id:
        raise HTTPException(
            status_code=403,
            detail="unlocking requires X-Signature-Id header",
        )
    if not verify_sig(pid, str(signature_id)):
        raise HTTPException(status_code=403, detail="signature invalid")
    return _lock.set_locked(pid, False, signature_id=str(signature_id))
