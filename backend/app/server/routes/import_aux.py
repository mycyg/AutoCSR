"""M21 — auxiliary document import routes.

    POST /api/projects/{pid}/import/protocol   (multipart pdf)
    POST /api/projects/{pid}/import/sap        (multipart docx)
    POST /api/projects/{pid}/import/define     (multipart xml)
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth.middleware import get_current_user
from app.auth.models import User
from app.config import data_dir
from app.ingestion.define_importer import import_define
from app.ingestion.protocol_importer import import_protocol
from app.ingestion.sap_importer import import_sap
from app.projects.manager import ensure_project_access
from app.server.upload_utils import ensure_child_path, sanitize_upload_filename

logger = logging.getLogger("autocsr.ingestion.routes")
router = APIRouter(tags=["ingest"])


def _save_upload(pid: str, kind: str, upload: UploadFile) -> Path:
    raw_dir = data_dir() / "projects" / pid / "raw" / "aux"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_upload_filename(upload.filename, f"{kind}.bin")
    target = ensure_child_path(raw_dir, safe_name)
    with target.open("wb") as f:
        f.write(upload.file.read())
    return target


@router.post("/projects/{pid}/import/protocol")
def import_protocol_endpoint(
    pid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    saved = _save_upload(pid, "protocol", file)
    try:
        result = import_protocol(pid, saved, source_filename=file.filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return json.loads(result.model_dump_json())


@router.post("/projects/{pid}/import/sap")
def import_sap_endpoint(
    pid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    saved = _save_upload(pid, "sap", file)
    try:
        result = import_sap(pid, saved, source_filename=file.filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return json.loads(result.model_dump_json())


@router.post("/projects/{pid}/import/define")
def import_define_endpoint(
    pid: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ensure_project_access(user, pid, "write")
    saved = _save_upload(pid, "define", file)
    try:
        result = import_define(pid, saved, source_filename=file.filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return json.loads(result.model_dump_json())
