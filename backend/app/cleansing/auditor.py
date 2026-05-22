"""Append-only audit log per project: data/projects/<pid>/audit.jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.schemas.cleansing import AuditLogEntry


def _audit_path(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log(project_id: str, file_id: str, action: str, **detail: Any) -> AuditLogEntry:
    entry = AuditLogEntry(
        timestamp=datetime.now(timezone.utc),
        project_id=project_id, file_id=file_id,
        action=action,
        proposal_id=detail.pop("proposal_id", None),
        snapshot_id=detail.pop("snapshot_id", None),
        rows_before=detail.pop("rows_before", None),
        rows_after=detail.pop("rows_after", None),
        detail=detail,
    )
    line = entry.model_dump_json()
    with _audit_path(project_id).open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return entry


def read_log(project_id: str, *, limit: int = 200) -> list[AuditLogEntry]:
    p = _audit_path(project_id)
    if not p.exists():
        return []
    out: list[AuditLogEntry] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(AuditLogEntry.model_validate_json(line))
        except Exception:
            continue
    return out
