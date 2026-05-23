"""Comments + Markers CRUD + batch apply (M11)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.config import data_dir
from app.report import comments as comments_mod
from app.report import markers as markers_mod
from app.server.ws import publish

logger = logging.getLogger("autocsr.routes.comments")
router = APIRouter(tags=["report"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/comments")
async def create_comment(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    node_id = str(body.get("node_id") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id required")
    paragraph_idx = int(body.get("paragraph_idx") or 0)
    rng = body.get("char_range") or [0, 0]
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        raise HTTPException(status_code=400, detail="char_range must be [start, end]")
    text = str(body.get("body") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="body text required")
    author = str(body.get("author") or "user")
    c = comments_mod.add_comment(
        pid, node_id=node_id, paragraph_idx=paragraph_idx,
        char_range=(int(rng[0]), int(rng[1])), body=text, author=author,
    )
    await publish(pid, "comment.created", {
        "id": c.id, "node_id": c.node_id, "paragraph_idx": c.paragraph_idx,
    })
    return c.model_dump()


@router.get("/projects/{pid}/comments")
def list_comments(pid: str,
                   node_id: str | None = Query(None),
                   status: str | None = Query(None)) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [c.model_dump() for c in comments_mod.list_comments(
        pid, node_id=node_id, status=status,
    )]


@router.patch("/projects/{pid}/comments/{cid}")
async def patch_comment(pid: str, cid: str,
                          body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    status = body.get("status")
    text = body.get("body")
    updated = comments_mod.update_comment(pid, cid,
                                           status=str(status) if status else None,
                                           body=str(text) if text else None)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"comment {cid} not found")
    await publish(pid, "comment.updated", {
        "id": updated.id, "status": updated.status,
    })
    return updated.model_dump()


@router.delete("/projects/{pid}/comments/{cid}")
async def delete_comment(pid: str, cid: str) -> dict[str, bool]:
    _ensure_project(pid)
    ok = comments_mod.delete_comment(pid, cid)
    if ok:
        await publish(pid, "comment.deleted", {"id": cid})
    return {"ok": ok}


@router.post("/projects/{pid}/comments/apply")
async def apply_comments(pid: str,
                           body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    try:
        result = await comments_mod.apply_all_unresolved(pid)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500,
                              detail=f"apply_all_unresolved failed: {e}")
    return result.model_dump()


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

@router.get("/projects/{pid}/markers")
def list_markers(pid: str,
                   node_id: str | None = Query(None)) -> list[dict[str, Any]]:
    _ensure_project(pid)
    if node_id:
        return markers_mod.list_markers(pid, node_id)
    return markers_mod.list_all_markers(pid)


@router.post("/projects/{pid}/markers")
async def create_marker(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    node_id = str(body.get("node_id") or "").strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id required")
    marker_type = str(body.get("type") or "important")
    rng = body.get("range") or [0, 0]
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        raise HTTPException(status_code=400, detail="range must be [start, end]")
    note = str(body.get("note") or "")
    color = body.get("color")
    m = markers_mod.add_marker(
        pid, node_id,
        marker_type=marker_type,
        range_=(int(rng[0]), int(rng[1])),
        note=note,
        color=str(color) if color else None,
    )
    if m is None:
        raise HTTPException(status_code=404, detail=f"draft {node_id} not found")
    await publish(pid, "marker.created", {
        "id": m.id, "node_id": node_id, "type": m.type,
    })
    return m.model_dump()


@router.delete("/projects/{pid}/markers/{marker_id}")
async def delete_marker(pid: str, marker_id: str,
                          node_id: str = Query(...)) -> dict[str, bool]:
    _ensure_project(pid)
    ok = markers_mod.delete_marker(pid, node_id, marker_id)
    if ok:
        await publish(pid, "marker.deleted", {"id": marker_id, "node_id": node_id})
    return {"ok": ok}
