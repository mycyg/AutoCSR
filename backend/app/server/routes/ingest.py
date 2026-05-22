"""Ingestion routes — kick off router+workers and probe progress."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import data_dir
from app.ingestion.orchestrator import (
    kick_off, project_status, load_result, load_entries,
)

router = APIRouter()


@router.post("/projects/{pid}/ingest")
def trigger_ingest(pid: str) -> dict[str, Any]:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    kick_off(pid)
    return {"project_id": pid, "kicked_off": True}


@router.get("/projects/{pid}/ingest_status")
def status(pid: str) -> dict[str, Any]:
    return project_status(pid)


@router.get("/projects/{pid}/ingest_result/{file_id}")
def file_result(pid: str, file_id: str) -> dict[str, Any]:
    r = load_result(pid, file_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"no ingest result for {file_id}")
    return r.model_dump()


@router.get("/projects/{pid}/files")
def list_files(pid: str) -> list[dict[str, Any]]:
    return [e.model_dump() for e in load_entries(pid)]
