"""V2-E (M14) — advanced statistics + TLF export routes."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from app.analysis.advanced.baseline_balance import smd_test
from app.analysis.advanced.consort import consort_flow
from app.analysis.advanced.multitest import multitest_adjust
from app.analysis.advanced.sensitivity import sensitivity_analysis
from app.analysis.advanced.subgroup import subgroup_analysis
from app.analysis.advanced.tlf_exporter import export_tlf, list_tlf_exports
from app.analysis.store import save as save_block
from app.config import data_dir
from app.server.ws import publish

logger = logging.getLogger("autocsr.analysis.advanced")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


def _resolve_parquet(pid: str, file_id: str | None) -> str | None:
    proc_dir = data_dir() / "projects" / pid / "processed"
    if not proc_dir.exists():
        return None
    if file_id:
        for ext in ("parquet", "csv"):
            for cand in proc_dir.glob(f"{file_id}*.{ext}"):
                return str(cand)
    # Fall back to first parquet
    for ext in ("parquet", "csv"):
        for cand in proc_dir.glob(f"*.{ext}"):
            return str(cand)
    return None


def _all_processed_parquets(pid: str) -> list[str]:
    proc_dir = data_dir() / "projects" / pid / "processed"
    if not proc_dir.exists():
        return []
    out: list[str] = []
    for ext in ("parquet", "csv"):
        out.extend(str(p) for p in proc_dir.glob(f"*.{ext}"))
    return out


def _project_output_dir(pid: str) -> str:
    p = data_dir() / "projects" / pid / "artifacts" / "advanced"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


# ---------------------------------------------------------------- multitest


@router.post("/projects/{pid}/analysis/multitest")
async def run_multitest(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    p_values = body.get("p_values") or []
    method = body.get("method") or "fdr_bh"
    labels = body.get("labels")
    alpha = float(body.get("alpha") or 0.05)
    if not p_values:
        raise HTTPException(status_code=400, detail="p_values required")
    try:
        p_values = [float(p) for p in p_values]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"p_values must be floats: {e}")
    block = await asyncio.to_thread(multitest_adjust, p_values, method, labels, alpha)
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "multitest", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


# ---------------------------------------------------------------- subgroup


@router.post("/projects/{pid}/analysis/subgroup")
async def run_subgroup(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    outcome_col = body.get("outcome_col")
    group_col = body.get("group_col")
    subgroup_cols = body.get("subgroup_cols") or []
    file_id = body.get("file_id")
    parquet = body.get("parquet_path") or _resolve_parquet(pid, file_id)
    if not parquet or not outcome_col or not group_col or not subgroup_cols:
        raise HTTPException(status_code=400,
                            detail="outcome_col, group_col, subgroup_cols and a resolvable parquet are required")
    block = await asyncio.to_thread(
        subgroup_analysis, parquet, outcome_col, group_col, list(subgroup_cols),
        output_dir=_project_output_dir(pid),
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "subgroup", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


# ---------------------------------------------------------------- sensitivity


@router.post("/projects/{pid}/analysis/sensitivity")
async def run_sensitivity(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    outcome_col = body.get("outcome_col")
    group_col = body.get("group_col")
    methods = body.get("methods") or ["itt", "pp", "locf", "mmrm"]
    file_id = body.get("file_id")
    parquet = body.get("parquet_path") or _resolve_parquet(pid, file_id)
    if not parquet or not outcome_col or not group_col:
        raise HTTPException(status_code=400,
                            detail="outcome_col, group_col and a resolvable parquet are required")
    blocks = await asyncio.to_thread(
        sensitivity_analysis, parquet, outcome_col, group_col, list(methods),
    )
    saved_ids: list[str] = []
    for b in blocks:
        s = await asyncio.to_thread(save_block, pid, b)
        saved_ids.append(s.id)
    await publish(pid, "analysis.done", {"mode": "sensitivity", "ids": saved_ids})
    return {"ids": saved_ids, "n": len(blocks)}


# ---------------------------------------------------------------- consort


@router.post("/projects/{pid}/analysis/consort")
async def run_consort(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    parquets = body.get("parquet_paths") or _all_processed_parquets(pid)
    if not parquets:
        raise HTTPException(status_code=400, detail="no processed parquet files available")
    block = await asyncio.to_thread(
        consort_flow, parquets, output_dir=_project_output_dir(pid),
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "consort", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


# ---------------------------------------------------------------- baseline


@router.post("/projects/{pid}/analysis/baseline_balance")
async def run_baseline_balance(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    group_col = body.get("group_col")
    vars_ = body.get("vars") or []
    file_id = body.get("file_id")
    threshold = float(body.get("threshold") or 0.1)
    parquet = body.get("parquet_path") or _resolve_parquet(pid, file_id)
    if not parquet or not group_col or not vars_:
        raise HTTPException(status_code=400,
                            detail="group_col, vars and a resolvable parquet are required")
    block = await asyncio.to_thread(
        smd_test, parquet, group_col, list(vars_), threshold,
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "baseline_balance", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


# ---------------------------------------------------------------- TLF export


@router.post("/projects/{pid}/export/tlf")
async def run_tlf_export(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    await publish(pid, "tlf.start", {})

    async def _do() -> dict[str, Any]:
        def _progress(phase: str, **meta: Any) -> None:
            # Sync callback — schedule the async publish without awaiting
            try:
                asyncio.run_coroutine_threadsafe(
                    publish(pid, f"tlf.{phase}", meta),
                    asyncio.get_event_loop(),
                )
            except Exception:
                pass
        try:
            out_path = await asyncio.to_thread(export_tlf, pid, progress=_progress)
        except Exception as e:
            logger.exception("tlf export failed")
            await publish(pid, "tlf.error", {"error": str(e)})
            raise HTTPException(status_code=500, detail=f"tlf export failed: {e}")
        size = out_path.stat().st_size
        await publish(pid, "tlf.done", {"filename": out_path.name, "size": size})
        return {"filename": out_path.name, "size_bytes": size, "path": str(out_path)}

    return await _do()


@router.get("/projects/{pid}/exports/tlf")
def list_tlf(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return list_tlf_exports(pid)


@router.get("/projects/{pid}/exports/tlf/{filename}")
def download_tlf(pid: str, filename: str):
    _ensure_project(pid)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    p = data_dir() / "projects" / pid / "exports" / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="export not found")
    return FileResponse(str(p), media_type="application/zip", filename=filename)
