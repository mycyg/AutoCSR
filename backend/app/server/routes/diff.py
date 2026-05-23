"""Multi-version draft diff (M11)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import data_dir
from app.report.diff import diff_markdown, diff_summary
from app.report.store import list_versions, load_draft, load_version

logger = logging.getLogger("autocsr.routes.diff")
router = APIRouter(tags=["report"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.get("/projects/{pid}/drafts/{node_id:path}/versions")
def list_draft_versions(pid: str, node_id: str) -> list[int]:
    _ensure_project(pid)
    return list_versions(pid, node_id)


@router.get("/projects/{pid}/drafts/{node_id:path}/diff")
def get_diff(pid: str, node_id: str,
              v1: int | None = Query(None),
              v2: int | None = Query(None)) -> dict[str, Any]:
    _ensure_project(pid)
    versions = list_versions(pid, node_id)
    # If v2 omitted use current; if v1 omitted use one prior
    if v1 is None and v2 is None and versions:
        if len(versions) >= 2:
            v1, v2 = versions[-2], versions[-1]
        else:
            v1 = v2 = versions[-1]
    md_v1: str
    md_v2: str
    if v1 is not None:
        d1 = load_version(pid, node_id, int(v1))
        if d1 is None:
            raise HTTPException(status_code=404, detail=f"version {v1} not found")
        md_v1 = d1.markdown
    else:
        md_v1 = ""
    if v2 is not None:
        d2 = load_version(pid, node_id, int(v2))
        if d2 is None:
            raise HTTPException(status_code=404, detail=f"version {v2} not found")
        md_v2 = d2.markdown
    else:
        # Use current draft
        cur = load_draft(pid, node_id)
        if cur is None:
            raise HTTPException(status_code=404, detail=f"draft {node_id} not found")
        md_v2 = cur.markdown
    blocks = diff_markdown(md_v1, md_v2)
    return {
        "node_id": node_id,
        "v1": v1, "v2": v2,
        "blocks": blocks,
        "summary": diff_summary(blocks),
    }
