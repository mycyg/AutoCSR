"""Audit + electronic signature routes (M15)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.audit import (
    list_signatures, load_signature, read_events, sign, verify, verify_chain,
)
from app.config import data_dir

router = APIRouter(tags=["audit"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/audit")
def list_events(
    pid: str,
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=500),
) -> list[dict[str, Any]]:
    _ensure_project(pid)
    s = _parse_dt(start)
    e = _parse_dt(end)
    events = read_events(pid, start=s, end=e, limit=limit)
    out = []
    for ev in events:
        if actor and ev.actor != actor:
            continue
        if action and action not in ev.action:
            continue
        if resource_type and ev.resource_type != resource_type:
            continue
        out.append(ev.model_dump())
    return out


@router.get("/projects/{pid}/audit/verify")
def verify_audit_chain(
    pid: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict[str, Any]:
    _ensure_project(pid)
    s = _parse_dt(start)
    e = _parse_dt(end)
    return verify_chain(pid, start=s, end=e).model_dump()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Electronic signatures
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/sign")
async def create_signature(
    pid: str, request: Request, body: dict = Body(...)
) -> dict[str, Any]:
    _ensure_project(pid)
    artifact_type = str(body.get("artifact_type") or "").strip()
    artifact_id = str(body.get("artifact_id") or "").strip()
    reason = str(body.get("reason") or "").strip()
    signer = str(body.get("signer") or request.headers.get("X-User-Id") or "anonymous")
    if not (artifact_type and artifact_id):
        raise HTTPException(
            status_code=400,
            detail="artifact_type and artifact_id required",
        )
    sig = sign(pid, artifact_type, artifact_id, signer, reason)
    return sig.model_dump()


@router.get("/projects/{pid}/signatures")
def list_all_signatures(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [s.model_dump() for s in list_signatures(pid)]


@router.get("/projects/{pid}/signatures/{sig_id}")
def get_signature(pid: str, sig_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    s = load_signature(pid, sig_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"signature {sig_id} not found")
    return s.model_dump()


@router.get("/projects/{pid}/signatures/{sig_id}/verify")
def verify_signature(pid: str, sig_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    s = load_signature(pid, sig_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"signature {sig_id} not found")
    return {"id": sig_id, "verified": bool(verify(pid, sig_id))}
