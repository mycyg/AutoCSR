"""Polish route (M20 v2.2).

  POST /api/projects/{pid}/polish/{node_id}
      body: {mode?: 'academic'|'concise'|'formal', markdown?: str}

If ``markdown`` is omitted we load the current draft for ``node_id``. If
the draft is missing we 404. We never auto-apply the polished text — the
client must POST the accepted polished_markdown back via the existing
chat-editor / draft-save endpoints.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.polishing_agent import polish
from app.config import data_dir
from app.report.store import load_draft

logger = logging.getLogger("autocsr.routes.polish")
router = APIRouter(tags=["report"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/polish/{node_id}")
async def polish_endpoint(pid: str, node_id: str,
                            body: dict = Body(default_factory=dict)
                            ) -> dict[str, Any]:
    _ensure_project(pid)
    mode = str((body or {}).get("mode") or "academic").lower()
    if mode not in ("academic", "concise", "formal"):
        raise HTTPException(status_code=400,
                             detail=f"invalid mode: {mode}")
    markdown = str((body or {}).get("markdown") or "").strip()
    if not markdown:
        draft = load_draft(pid, node_id)
        if draft is None:
            raise HTTPException(status_code=404,
                                 detail=f"no draft for node {node_id}; "
                                          "pass markdown explicitly")
        markdown = draft.markdown or ""
    if not markdown.strip():
        raise HTTPException(status_code=400, detail="markdown is empty")

    try:
        result = await polish(markdown, mode=mode,
                                project_id=pid, node_id=node_id)
    except Exception as e:        # noqa: BLE001
        logger.exception("polish failed")
        raise HTTPException(status_code=500,
                             detail=f"polish failed: {e}")

    payload = result.model_dump()
    payload["node_id"] = node_id
    return payload
