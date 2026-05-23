"""eCTD M5.3.5 packaging routes (M17).

Endpoints
---------
POST /api/projects/{pid}/export/ectd          (multipart, 3 optional files)
GET  /api/projects/{pid}/exports/ectd          (history)
GET  /api/projects/{pid}/exports/ectd/{filename}  (download)
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import data_dir
from app.export.ectd_packager import (
    ectd_export_path, list_ectd_exports, package_ectd,
)

logger = logging.getLogger("autocsr.server.routes.ectd")

router = APIRouter(tags=["export"])

# Simple in-memory task tracker so the GET /api/tasks/{task_id}/status
# pattern used elsewhere works for eCTD too. Persisting this would be
# overkill — the zip itself is the source of truth.
_TASKS: dict[str, dict[str, Any]] = {}


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


async def _publish(pid: str, event: str, payload: dict) -> None:
    try:
        from app.server.ws import publish
        await publish(pid, event, payload)
    except Exception:
        pass


@router.post("/projects/{pid}/export/ectd")
async def run_ectd_export(
    pid: str,
    cover_letter: UploadFile | None = File(default=None),
    investigator_statement: UploadFile | None = File(default=None),
    icf: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    _ensure_project(pid)
    task_id = "ectd_" + uuid.uuid4().hex[:10]
    _TASKS[task_id] = {"status": "running", "filename": None}

    await _publish(pid, "ectd.start", {"task_id": task_id})

    async def _stash(upload: UploadFile | None) -> Path | None:
        if upload is None:
            return None
        raw = await upload.read()
        if not raw:
            return None
        tmp = Path(tempfile.mkstemp(suffix="-" + (upload.filename or "f.bin"))[1])
        tmp.write_bytes(raw)
        return tmp

    cover_path = await _stash(cover_letter)
    inv_path = await _stash(investigator_statement)
    icf_path = await _stash(icf)

    try:
        out_path = await asyncio.to_thread(
            package_ectd, pid,
            cover_letter_path=cover_path,
            investigator_statement_path=inv_path,
            icf_path=icf_path,
        )
    except FileNotFoundError as e:
        _TASKS[task_id] = {"status": "error", "error": str(e)}
        await _publish(pid, "ectd.error", {"task_id": task_id, "error": str(e)})
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("ectd packaging failed")
        _TASKS[task_id] = {"status": "error", "error": str(e)}
        await _publish(pid, "ectd.error", {"task_id": task_id, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"ectd packaging failed: {e}")
    finally:
        # Best-effort cleanup of the uploaded temp files
        for p in (cover_path, inv_path, icf_path):
            try:
                if p is not None and Path(p).exists():
                    Path(p).unlink()
            except Exception:
                pass

    size = out_path.stat().st_size
    _TASKS[task_id] = {
        "status": "done", "filename": out_path.name, "size_bytes": size,
    }
    await _publish(pid, "ectd.done", {
        "task_id": task_id, "filename": out_path.name, "size_bytes": size,
    })
    return {
        "task_id": task_id,
        "filename": out_path.name,
        "size_bytes": size,
    }


@router.get("/projects/{pid}/exports/ectd")
def list_ectd(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return list_ectd_exports(pid)


@router.get("/projects/{pid}/exports/ectd/{filename}")
def download_ectd(pid: str, filename: str):
    _ensure_project(pid)
    p = ectd_export_path(pid, filename)
    if p is None:
        raise HTTPException(status_code=404, detail="ectd export not found")
    return FileResponse(str(p), media_type="application/zip", filename=filename)
