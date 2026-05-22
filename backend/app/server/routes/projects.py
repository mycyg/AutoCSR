"""Project CRUD — M1 surface.

Storage: a single JSON file `<data_dir>/projects.json` holding a list of
serialized Project records. Per-project artefacts live under
`<data_dir>/projects/<pid>/{raw,processed,corpus,chapters,exports,chats}`.

M2 will migrate to a SQLite index when concurrency matters.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import data_dir
from app.schemas.project import Project, ProjectCreate

router = APIRouter()

_LOCK = threading.RLock()

_SUBDIRS = ("raw", "processed", "corpus", "chapters", "exports", "chats")


def _projects_json() -> Path:
    return data_dir() / "projects.json"


def _load_all() -> list[dict[str, Any]]:
    p = _projects_json()
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else []
    except json.JSONDecodeError:
        return []


def _save_all(items: list[dict[str, Any]]) -> None:
    p = _projects_json()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _project_dir(pid: str) -> Path:
    return data_dir() / "projects" / pid


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    with _LOCK:
        return _load_all()


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict[str, Any]:
    pid = uuid.uuid4().hex[:12]
    proj = Project(
        id=pid,
        name=body.name.strip(),
        principle_id=body.principle_id,
        created_at=datetime.now(timezone.utc),
        status="draft",
    )
    with _LOCK:
        items = _load_all()
        items.append(json.loads(proj.model_dump_json()))
        _save_all(items)
    # Materialize per-project subdirs so downstream writers don't race on mkdir.
    pdir = _project_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pdir / sub).mkdir(exist_ok=True)
    return json.loads(proj.model_dump_json())


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict[str, Any]:
    with _LOCK:
        for item in _load_all():
            if item.get("id") == pid:
                return item
    raise HTTPException(status_code=404, detail=f"project {pid} not found")
