"""M21 — 4 advanced visualization endpoints + 1 generic.

POST /api/projects/{pid}/analysis/km_with_risk     body {file_id?, time_col?, event_col?, group_col?, time_points?}
POST /api/projects/{pid}/analysis/bland_altman     body {file_id?, col_method1, col_method2}
POST /api/projects/{pid}/analysis/heatmap          body {file_id?, row_col, col_col, value_col, aggfunc?}
POST /api/projects/{pid}/analysis/pk_profile_3d    body {file_id?, subject_col?, time_col?, conc_col?}
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.analysis.advanced.bland_altman import bland_altman
from app.analysis.advanced.heatmap import heatmap
from app.analysis.advanced.km_with_risk import km_with_risk_table
from app.analysis.advanced.pk_profile_3d import pk_profile_3d
from app.analysis.store import save as save_block
from app.auth.middleware import get_current_user
from app.auth.models import User
from app.config import data_dir
from app.projects.manager import ensure_project_access
from app.server.ws import publish

logger = logging.getLogger("autocsr.analysis.viz")
router = APIRouter(tags=["analysis"])


def _resolve_parquet(pid: str, file_id: str | None,
                       explicit: str | None) -> str | None:
    if explicit:
        return explicit
    proc_dir = data_dir() / "projects" / pid / "processed"
    if not proc_dir.exists():
        return None
    if file_id:
        for ext in ("parquet", "csv"):
            for cand in proc_dir.glob(f"{file_id}*.{ext}"):
                return str(cand)
    for ext in ("parquet", "csv"):
        for cand in proc_dir.glob(f"*.{ext}"):
            return str(cand)
    return None


@router.post("/projects/{pid}/analysis/km_with_risk")
async def run_km_with_risk(pid: str, body: dict = Body(default_factory=dict),
                            user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    parquet = _resolve_parquet(pid, body.get("file_id"), body.get("parquet_path"))
    if not parquet:
        raise HTTPException(status_code=400, detail="no processed parquet found")
    block = await asyncio.to_thread(
        km_with_risk_table,
        parquet,
        body.get("time_col") or "AVAL",
        body.get("event_col") or "CNSR",
        body.get("group_col"),
        body.get("time_points"),
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "km_with_risk", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


@router.post("/projects/{pid}/analysis/bland_altman")
async def run_bland_altman(pid: str, body: dict = Body(...),
                            user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    col_method1 = body.get("col_method1")
    col_method2 = body.get("col_method2")
    if not col_method1 or not col_method2:
        raise HTTPException(status_code=400,
                            detail="col_method1 and col_method2 required")
    parquet = _resolve_parquet(pid, body.get("file_id"), body.get("parquet_path"))
    if not parquet:
        raise HTTPException(status_code=400, detail="no processed parquet found")
    block = await asyncio.to_thread(bland_altman, parquet, col_method1, col_method2)
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "bland_altman", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


@router.post("/projects/{pid}/analysis/heatmap")
async def run_heatmap(pid: str, body: dict = Body(...),
                       user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    row_col = body.get("row_col")
    col_col = body.get("col_col")
    value_col = body.get("value_col")
    if not (row_col and col_col and value_col):
        raise HTTPException(status_code=400,
                            detail="row_col, col_col, value_col required")
    parquet = _resolve_parquet(pid, body.get("file_id"), body.get("parquet_path"))
    if not parquet:
        raise HTTPException(status_code=400, detail="no processed parquet found")
    block = await asyncio.to_thread(
        heatmap, parquet, row_col, col_col, value_col, body.get("aggfunc") or "mean",
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "heatmap", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}


@router.post("/projects/{pid}/analysis/pk_profile_3d")
async def run_pk_profile_3d(pid: str, body: dict = Body(default_factory=dict),
                              user: User = Depends(get_current_user)) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    parquet = _resolve_parquet(pid, body.get("file_id"), body.get("parquet_path"))
    if not parquet:
        raise HTTPException(status_code=400, detail="no processed parquet found")
    block = await asyncio.to_thread(
        pk_profile_3d,
        parquet,
        body.get("subject_col") or "USUBJID",
        body.get("time_col") or "PCDTC",
        body.get("conc_col") or "PCSTRESN",
    )
    saved = await asyncio.to_thread(save_block, pid, block)
    await publish(pid, "analysis.done", {"mode": "pk_profile_3d", "ids": [saved.id]})
    return {"id": saved.id, "block": saved.model_dump()}
