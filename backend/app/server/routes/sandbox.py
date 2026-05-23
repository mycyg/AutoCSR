"""Sandbox routes (M7).

  POST /api/projects/{pid}/sandbox/run   {code, timeout?, mem_mb?, additional_data_paths?}
  GET  /api/projects/{pid}/sandbox/runs
  GET  /api/projects/{pid}/sandbox/runs/{run_id}/artifacts/{filename}
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from app.auth.middleware import get_current_user
from app.auth.models import User
from app.config import data_dir
from app.config.project_config import get_config as cfg_get
from app.projects.manager import ensure_project_access
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


def _coerce_int(value: Any, default: int, *, name: str, minimum: int = 1) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be an integer") from exc
    if parsed < minimum:
        raise HTTPException(status_code=400, detail=f"{name} must be >= {minimum}")
    return parsed


def _resolve_additional_paths(pid: str, values: list[Any]) -> list[str]:
    project_root = (data_dir() / "projects" / pid).resolve()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail="additional_data_paths entries must be strings")
        raw = value.strip()
        if not raw:
            continue
        base = Path(raw)
        candidate = base.resolve() if base.is_absolute() else (project_root / base).resolve()
        try:
            candidate.relative_to(project_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="additional_data_paths must stay within the project directory",
            ) from exc
        if candidate.exists():
            out.append(str(candidate))
    return out


@router.post("/projects/{pid}/sandbox/run")
async def run_sandbox(
    pid: str,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    cfg = cfg_get(pid)
    if not cfg.sandbox_enabled:
        raise HTTPException(status_code=403, detail="sandbox disabled for this project")
    code = body.get("code")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="code (string) required")
    timeout = _coerce_int(body.get("timeout"), cfg.sandbox_timeout_s, name="timeout")
    mem_mb = _coerce_int(body.get("mem_mb"), cfg.sandbox_mem_mb, name="mem_mb")
    additional = body.get("additional_data_paths") or []
    if not isinstance(additional, list):
        raise HTTPException(status_code=400, detail="additional_data_paths must be a list")
    additional_paths = _resolve_additional_paths(pid, additional)

    await publish(pid, "sandbox.run_start",
                  {"timeout": timeout, "mem_mb": mem_mb})

    def _do() -> dict[str, Any]:
        res = execute_python(
            pid, code,
            timeout=timeout, mem_mb=mem_mb,
            additional_data_paths=additional_paths,
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
def list_sandbox_runs(
    pid: str,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ensure_project_access(user, pid, "read")
    return list_runs(pid)


@router.get("/projects/{pid}/sandbox/runs/{run_id}/artifacts/{filename}")
def get_artifact(
    pid: str,
    run_id: str,
    filename: str,
    user: User = Depends(get_current_user),
):
    ensure_project_access(user, pid, "read")
    p = artifact_path(pid, run_id, filename)
    if p is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(path=str(p), filename=filename)
