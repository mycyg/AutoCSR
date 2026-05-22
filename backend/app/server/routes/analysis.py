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
            try:
                from app.state import default_machine, ProjectState
                default_machine.try_transition(pid, ProjectState.analyzed,
                                                reason=f"auto +{len(blocks)} blocks")
            except Exception:
                pass
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


# ---------------------------------------------------------------------------
# M8: natural language data Q&A
# ---------------------------------------------------------------------------


@router.post("/projects/{pid}/ask")
async def ask_data(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    """Run the analyst agent and return the resulting StatBlock + run id."""
    _ensure_project(pid)
    from app.agents.analyst_agent import AnalystAgent
    from app.schemas.agent import AgentInput

    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    scope = body.get("scope") or "all"
    parquet_paths = body.get("parquet_paths") or []
    timeout = int(body.get("sandbox_timeout_s") or 60)
    mem_mb = int(body.get("sandbox_mem_mb") or 1024)

    agent = AnalystAgent()
    ai = AgentInput(
        project_id=pid,
        payload={
            "query": query,
            "scope": scope,
            "parquet_paths": parquet_paths,
            "sandbox_timeout_s": timeout,
            "sandbox_mem_mb": mem_mb,
        },
        meta={"caller": "/ask"},
    )
    try:
        ao = await agent.run(ai)
    except Exception as e:  # noqa: BLE001
        await publish(pid, "analyst.error", {"msg": str(e)[:300]})
        raise HTTPException(status_code=500, detail=f"analyst failed: {e}")
    return ao.result or {}


@router.get("/projects/{pid}/ask/history")
def ask_history(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    from app.agents.analyst_agent import list_ask_history

    return list_ask_history(pid)
