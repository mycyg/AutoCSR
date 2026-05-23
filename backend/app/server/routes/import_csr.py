"""CSR reverse-import routes (M13).

  POST /api/projects/{pid}/import/csr            (multipart docx)
  POST /api/projects/{pid}/import/csr/commit     body: {import_id, principle_id?}
  GET  /api/projects/{pid}/import/csr/{import_id}
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from app.config import data_dir
from app.ingestion.csr_importer import (
    commit_import, get_import, import_csr,
)

logger = logging.getLogger("autocsr.import_csr")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/import/csr")
async def upload_csr(pid: str, file: UploadFile = File(...)) -> dict[str, Any]:
    _ensure_project(pid)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")
    # Drop to a tmp file because python-docx wants a path / file-like
    tmp = Path(tempfile.mkdtemp(prefix="autocsr_import_")) / (file.filename or "uploaded.docx")
    tmp.write_bytes(raw)
    try:
        result = import_csr(pid, tmp)
    except Exception as e:  # noqa: BLE001
        logger.exception("csr import failed")
        raise HTTPException(status_code=400, detail=f"import failed: {e}") from e
    return result.model_dump()


@router.get("/projects/{pid}/import/csr/{import_id}")
def get_csr_import(pid: str, import_id: str) -> dict[str, Any]:
    _ensure_project(pid)
    res = get_import(import_id)
    if res is None or res.project_id != pid:
        raise HTTPException(status_code=404, detail=f"import {import_id} not found")
    return res.model_dump()


@router.post("/projects/{pid}/import/csr/commit")
def commit_csr_import(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    import_id = str(body.get("import_id") or "").strip()
    if not import_id:
        raise HTTPException(status_code=400, detail="import_id is required")
    principle_id = body.get("principle_id") or None
    try:
        return commit_import(pid, import_id, principle_id=principle_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("csr commit failed")
        raise HTTPException(status_code=500, detail=f"commit failed: {e}") from e
