"""Admin / introspection routes (M6).

  GET    /api/projects/{pid}/config   -> ProjectConfig
  PATCH  /api/projects/{pid}/config   -> updated ProjectConfig
  GET    /api/projects/{pid}/state    -> {state, history}
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.config import data_dir
from app.config.project_config import (
    get_config as cfg_get,
    save_config as cfg_save,
)
from app.state import default_machine

router = APIRouter(tags=["admin"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.get("/projects/{pid}/config")
def get_project_config(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    return cfg_get(pid).model_dump()


@router.patch("/projects/{pid}/config")
def patch_project_config(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    merged = cfg_save(pid, body)
    return merged.model_dump()


@router.get("/projects/{pid}/state")
def get_project_state(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    return default_machine.get_record(pid)
