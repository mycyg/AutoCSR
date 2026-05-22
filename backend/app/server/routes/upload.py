"""File upload: POST /projects/{pid}/upload (multipart, multiple files)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import data_dir
from app.ingestion.orchestrator import load_entries, stamp_uploaded

router = APIRouter()


def _project_dir(pid: str) -> Path:
    return data_dir() / "projects" / pid


@router.post("/projects/{pid}/upload")
async def upload_files(pid: str, files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not _project_dir(pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")
    out: list[dict[str, Any]] = []
    for upload in files:
        file_id = uuid.uuid4().hex[:12]
        dest_dir = _project_dir(pid) / "raw" / file_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = upload.filename or f"file_{file_id}"
        dest = dest_dir / safe_name
        data = await upload.read()
        dest.write_bytes(data)
        entry = stamp_uploaded(
            pid, file_id, safe_name, dest,
            mime=upload.content_type, size_bytes=len(data),
        )
        out.append({
            "file_id": entry.file_id, "filename": entry.filename,
            "size_bytes": entry.size_bytes, "stored_path": entry.stored_path,
            "status": entry.status,
        })
    return {"project_id": pid, "uploaded": out,
            "total_entries": len(load_entries(pid))}
