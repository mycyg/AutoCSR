"""Literature search route (M20 v2.2).

  POST /api/projects/{pid}/literature_search
      body: {query, source: 'pubmed'|'wanfang', max_results?, ingest?}
      returns: {query, source, count, papers, ingested_block_ids?}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.literature_search import (
    ingest_papers_to_corpus,
    search_literature,
)
from app.config import data_dir

logger = logging.getLogger("autocsr.routes.literature_search")
router = APIRouter(tags=["admin"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/literature_search")
async def search_endpoint(pid: str,
                            body: dict = Body(default_factory=dict)
                            ) -> dict[str, Any]:
    _ensure_project(pid)
    query = str((body or {}).get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    source = str((body or {}).get("source") or "pubmed").lower()
    max_results = int((body or {}).get("max_results") or 10)
    do_ingest = bool((body or {}).get("ingest", False))

    try:
        result = await asyncio.to_thread(
            search_literature, query,
            source=source, max_results=max_results, project_id=pid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:        # noqa: BLE001
        logger.exception("literature_search failed")
        raise HTTPException(status_code=500,
                             detail=f"literature_search failed: {e}")

    if do_ingest and result.get("papers"):
        try:
            ids = await asyncio.to_thread(
                ingest_papers_to_corpus, pid, result["papers"],
            )
            result["ingested_block_ids"] = ids
        except Exception as e:    # noqa: BLE001
            logger.warning("ingest_failed: %s", e)
            result["ingested_block_ids"] = []
            result["ingest_warning"] = str(e)[:200]

    return result
