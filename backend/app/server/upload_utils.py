"""Helpers for safely handling user supplied upload filenames."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from app.config import data_dir

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_upload_filename(filename: str | None, default: str) -> str:
    """Return a basename-only filename safe to join under a storage directory."""
    raw = (filename or default).replace("\\", "/")
    name = Path(raw).name.strip()
    name = _CONTROL_CHARS.sub("_", name)
    if name in {"", ".", ".."}:
        name = default
    return name[:255] or default


def ensure_child_path(parent: Path, child_name: str) -> Path:
    """Resolve ``child_name`` below ``parent`` and reject traversal attempts."""
    parent_resolved = parent.resolve()
    candidate = (parent / child_name).resolve()
    if candidate.parent != parent_resolved:
        raise HTTPException(status_code=400, detail="invalid filename")
    return candidate


def project_root(project_id: str) -> Path:
    return (data_dir() / "projects" / project_id).resolve()


def ensure_project_file(project_id: str, path_value: str | Path,
                        *, subdir: str | None = None) -> Path:
    """Resolve a caller-supplied path and require it to stay inside a project.

    Absolute paths are accepted only when they resolve below the project root
    (or below ``subdir`` when supplied). Relative paths are resolved under the
    project root. This keeps analysis routes from reading arbitrary local files.
    """
    base = project_root(project_id)
    allowed = (base / subdir).resolve() if subdir else base
    raw = Path(path_value)
    candidate = raw.resolve() if raw.is_absolute() else (base / raw).resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        raise HTTPException(status_code=400, detail="path outside project")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="project file not found")
    return candidate
