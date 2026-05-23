"""Sandbox routes (M7).

  POST /api/projects/{pid}/sandbox/run   {code, timeout?, mem_mb?, additional_data_paths?}
  GET  /api/projects/{pid}/sandbox/runs
  GET  /api/projects/{pid}/sandbox/runs/{run_id}/artifacts/{filename}
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from app.config import data_dir
from app.config.project_config import get_config as cfg_get
from app.sandbox.executor import (
    artifact_path,
    execute_python,
    list_runs,
)
from app.server.ws import publish

router = APIRouter(tags=["admin"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/sandbox/run")
async def run_sandbox(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    cfg = cfg_get(pid)
    if not cfg.sandbox_enabled:
        raise HTTPException(status_code=403, detail="sandbox disabled for this project")
    code = body.get("code")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="code (string) required")
    timeout = int(body.get("timeout") or cfg.sandbox_timeout_s)
    mem_mb = int(body.get("mem_mb") or cfg.sandbox_mem_mb)
    additional = body.get("additional_data_paths") or []
    if not isinstance(additional, list):
        raise HTTPException(status_code=400, detail="additional_data_paths must be a list")

    await publish(pid, "sandbox.run_start",
                  {"timeout": timeout, "mem_mb": mem_mb})

    def _do() -> dict[str, Any]:
        res = execute_python(
            pid, code,
            timeout=timeout, mem_mb=mem_mb,
            additional_data_paths=[str(p) for p in additional],
        )
        return res.to_dict()

    result = await asyncio.to_thread(_do)
    await publish(pid, "sandbox.run_done", {
        "run_id": result["run_id"],
        "exit_code": result["exit_code"],
        "error": result.get("error"),
        "duration_ms": result["duration_ms"],
        "n_artifacts": len(result.get("artifacts", [])),
    })
    return result


@router.get("/projects/{pid}/sandbox/runs")
def list_sandbox_runs(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return list_runs(pid)


@router.get("/projects/{pid}/sandbox/runs/{run_id}/artifacts/{filename}")
def get_artifact(pid: str, run_id: str, filename: str):
    _ensure_project(pid)
    p = artifact_path(pid, run_id, filename)
    if p is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path=str(p), filename=filename)
