"""Analysis routes — auto-analyze hook, manual run, list / get / delete StatBlocks."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.analysis import descriptive, inferential, safety, survival
from app.analysis.auto import auto_analyze
from app.analysis.store import (
    delete as delete_block, get as get_block, list_blocks, save as save_block, search as search_blocks,
)
from app.config import data_dir
from app.server.ws import publish

logger = logging.getLogger("autocsr.analysis.routes")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/analysis/auto")
async def trigger_auto(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    await publish(pid, "analysis.start", {"mode": "auto"})

    async def _runner() -> None:
        try:
            blocks = await asyncio.to_thread(auto_analyze, pid)
            await publish(pid, "analysis.done", {
                "mode": "auto",
                "n_blocks": len(blocks),
                "ids": [b.id for b in blocks],
            })
        except Exception as e:
            logger.exception("auto_analyze failed")
            await publish(pid, "analysis.error", {"error": str(e)})

    # Run inline-ish: schedule in background but also return a sync summary
    # so the e2e test can act on it deterministically.
    task = asyncio.create_task(_runner())
    # Wait briefly (most projects: a few seconds). Cap to keep request fast.
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=120)
    except asyncio.TimeoutError:
        return {"started": True, "status": "running"}
    return {"started": True, "status": "done", "blocks": list_blocks(pid)}


@router.post("/projects/{pid}/analysis/run")
async def run_one(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    kind = body.get("type")
    params = body.get("params") or {}
    if not kind:
        raise HTTPException(status_code=400, detail="type required")
    await publish(pid, "analysis.start", {"mode": "manual", "type": kind})

    def _run() -> Any:
        if kind == "descriptive":
            return descriptive.baseline_table(**params)
        if kind == "inferential":
            return inferential.compare_groups(**params)
        if kind == "survival_km":
            return survival.km_estimate(**params)
        if kind == "survival_cox":
            return survival.cox_regression(**params)
        if kind == "safety":
            return safety.ae_summary(**params)
        raise ValueError(f"unsupported analysis type: {kind}")

    try:
        block = await asyncio.to_thread(_run)
    except Exception as e:
        await publish(pid, "analysis.error", {"error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "manual", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


@router.get("/projects/{pid}/stats")
def list_stats_endpoint(
    pid: str,
    analysis_type: str | None = Query(None),
    q: str | None = Query(None),
) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return search_blocks(pid, analysis_type=analysis_type, title_query=q)  # type: ignore[arg-type]


@router.get("/projects/{pid}/stats/{stat_id}")
def get_stat(pid: str, stat_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    block = get_block(pid, stat_id)
    if not block:
        raise HTTPException(status_code=404, detail="stat block not found")
    return block.model_dump()


@router.delete("/projects/{pid}/stats/{stat_id}")
def delete_stat(pid: str, stat_id: str) -> dict[str, bool]:
    _ensure_project(pid)
    return {"ok": delete_block(pid, stat_id)}
