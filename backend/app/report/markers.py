"""Markers (M11) — colored annotations on SectionDraft text.

Markers live on the SectionDraft itself (``draft.markers``) so version
snapshots carry them forward. They're persisted whenever a draft is
saved; this module provides the CRUD layer the routes hit.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.report import store as draft_store
from app.schemas.marker import Marker, default_color


def _ensure_markers(draft) -> list[dict[str, Any]]:
    markers = list(draft.markers or [])
    return markers


def list_markers(pid: str, node_id: str) -> list[dict[str, Any]]:
    draft = draft_store.load_draft(pid, node_id)
    if draft is None:
        return []
    return _ensure_markers(draft)


def add_marker(pid: str, node_id: str, *, marker_type: str,
                range_: tuple[int, int], note: str = "",
                color: str | None = None) -> Marker | None:
    draft = draft_store.load_draft(pid, node_id)
    if draft is None:
        return None
    if marker_type not in ("important", "todo", "question", "risk"):
        marker_type = "important"
    m = Marker(
        id=uuid.uuid4().hex[:10],
        node_id=node_id,
        type=marker_type,  # type: ignore[arg-type]
        color=color or default_color(marker_type),
        range=(int(range_[0]), int(range_[1])),
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    markers = _ensure_markers(draft)
    markers.append(m.model_dump(mode="json"))
    new_draft = draft.model_copy(update={"markers": markers})
    draft_store.save_draft(pid, new_draft)
    return m


def delete_marker(pid: str, node_id: str, marker_id: str) -> bool:
    draft = draft_store.load_draft(pid, node_id)
    if draft is None:
        return False
    markers = _ensure_markers(draft)
    new_markers = [m for m in markers if m.get("id") != marker_id]
    if len(new_markers) == len(markers):
        return False
    new_draft = draft.model_copy(update={"markers": new_markers})
    draft_store.save_draft(pid, new_draft)
    return True


def list_all_markers(pid: str) -> list[dict[str, Any]]:
    """Aggregate markers across every section of a project."""
    out: list[dict[str, Any]] = []
    for d in draft_store.list_drafts(pid):
        for m in (d.markers or []):
            if isinstance(m, dict):
                out.append({**m, "node_id": d.node_id})
    return out
