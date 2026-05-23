"""Project zip backup + restore routes (M19).

Endpoints:
  POST /api/projects/{pid}/backup     → zip the whole project dir, return file
  POST /api/projects/restore (multipart zip) → unpack into a fresh pid

The manifest baked into the zip captures source pid + size + file count so
restore can sanity-check the upload before extracting. Sensitive material
(keys/, signatures/private keys) is intentionally excluded.
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import data_dir

router = APIRouter(tags=["projects"])
logger = logging.getLogger("autocsr.backup")


EXCLUDE_DIRS = {"keys", "__pycache__"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}


@dataclass
class BackupManifest:
    source_pid: str
    created_at: str
    data_size: int
    file_count: int
    autocsr_version: str = "v2.x"

    def to_json(self) -> str:
        from dataclasses import asdict
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def _project_dir(pid: str) -> Path:
    return data_dir() / "projects" / pid


def _iter_project_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            if path.name in EXCLUDE_DIRS:
                # Skip the entire subtree by yielding nothing for descendants.
                # rglob will still walk into it; we filter below.
                continue
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        yield path


@router.post("/projects/{pid}/backup")
def backup_project(pid: str):
    """Pack the project dir into a downloadable zip."""
    src = _project_dir(pid)
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")

    backups = data_dir() / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backups / f"project_{pid}_{ts}.zip"

    file_count = 0
    data_size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _iter_project_files(src):
            rel = path.relative_to(src)
            zf.write(path, arcname=str(Path("project") / rel))
            file_count += 1
            try:
                data_size += path.stat().st_size
            except Exception:
                pass
        manifest = BackupManifest(
            source_pid=pid,
            created_at=datetime.now().isoformat(timespec="seconds"),
            data_size=data_size,
            file_count=file_count,
        )
        zf.writestr("manifest.json", manifest.to_json())

    logger.info("backup pid=%s files=%d bytes=%d → %s", pid, file_count, data_size, out.name)
    return FileResponse(
        path=str(out),
        filename=out.name,
        media_type="application/zip",
        headers={"X-AutoCSR-Backup-Pid": pid,
                 "X-AutoCSR-Backup-Files": str(file_count),
                 "X-AutoCSR-Backup-Bytes": str(data_size)},
    )


@router.post("/projects/restore")
async def restore_project(file: UploadFile = File(...)) -> dict[str, Any]:
    """Unpack a previously-backed-up project into a fresh pid.

    The new project id is generated server-side so restored copies can
    coexist with the source project on the same host.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="upload must be a .zip backup")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail=f"not a valid zip: {e}") from e

    names = zf.namelist()
    if "manifest.json" not in names:
        raise HTTPException(status_code=400, detail="backup missing manifest.json")
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad manifest: {e}") from e

    new_pid = f"r_{uuid.uuid4().hex[:12]}"
    target = _project_dir(new_pid)
    if target.exists():
        raise HTTPException(status_code=500, detail="generated pid collision; retry")
    target.mkdir(parents=True, exist_ok=True)

    extracted = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        zf.extractall(tmpdir)
        project_root = Path(tmpdir) / "project"
        if not project_root.exists():
            # Tolerate older backups that put files at the zip root.
            project_root = Path(tmpdir)
        for path in project_root.rglob("*"):
            if path.is_dir():
                continue
            if path.name in EXCLUDE_FILES:
                continue
            rel = path.relative_to(project_root)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            extracted += 1

    # Register the new project in projects.json so the frontend lists it.
    pj = data_dir() / "projects.json"
    items: list[dict[str, Any]] = []
    if pj.exists():
        try:
            items = json.loads(pj.read_text(encoding="utf-8") or "[]")
        except Exception:
            items = []
    name = f"Restored from {manifest.get('source_pid', '?')[:8]}"
    items.append({
        "id": new_pid,
        "name": name,
        "principle_id": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "intake",
        "tags": ["restored"],
        "archived": False,
        "last_opened_at": None,
        "language": "zh",
        "notes": f"Restored from backup of {manifest.get('source_pid')}",
        "template_id": None,
    })
    pj.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("restore pid=%s ← source=%s files=%d",
                new_pid, manifest.get("source_pid"), extracted)
    return {
        "ok": True,
        "new_pid": new_pid,
        "name": name,
        "source_pid": manifest.get("source_pid"),
        "files_restored": extracted,
        "manifest": manifest,
    }
