"""Outline persistence — current outline + archived versions.

Layout per project:
    data/projects/<pid>/outline.json              — current (latest version)
    data/projects/<pid>/outline_v{N}.json         — archive of every version

Mutation helpers (update_node / add_child / delete_node) operate on the current
outline and bump `updated_at`.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.schemas.outline import Outline, OutlineNode

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _LOCKS_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _proj_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid
    p.mkdir(parents=True, exist_ok=True)
    return p


def _current_path(pid: str) -> Path:
    return _proj_dir(pid) / "outline.json"


def _version_path(pid: str, version: int) -> Path:
    return _proj_dir(pid) / f"outline_v{version}.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save(outline: Outline) -> Outline:
    """Persist outline as both `outline.json` and an archived versioned copy."""
    payload = json.loads(outline.model_dump_json())
    with _lock(outline.project_id):
        _current_path(outline.project_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _version_path(outline.project_id, outline.version).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return outline


def load(pid: str) -> Outline | None:
    p = _current_path(pid)
    if not p.exists():
        return None
    try:
        return Outline.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_versions(pid: str) -> list[int]:
    versions: list[int] = []
    for p in _proj_dir(pid).glob("outline_v*.json"):
        try:
            versions.append(int(p.stem.split("_v", 1)[1]))
        except ValueError:
            continue
    return sorted(versions)


def restore_version(pid: str, version: int) -> Outline | None:
    """Replace the current outline with an archived version.

    Bumps the version number so we never overwrite history.
    """
    src = _version_path(pid, version)
    if not src.exists():
        return None
    try:
        old = Outline.model_validate_json(src.read_text(encoding="utf-8"))
    except Exception:
        return None
    next_v = max(list_versions(pid) + [version]) + 1
    restored = old.model_copy(update={
        "version": next_v,
        "updated_at": _now(),
        "notes": list(old.notes) + [f"restored_from_v{version}"],
    })
    save(restored)
    return restored


def next_version(pid: str) -> int:
    return max([0, *list_versions(pid)]) + 1


# ---------------------------------------------------------------------------
# Node mutation helpers
# ---------------------------------------------------------------------------

def _find_node_and_parent(
    nodes: list[OutlineNode], node_id: str, parent: OutlineNode | None = None,
) -> tuple[OutlineNode | None, OutlineNode | None, list[OutlineNode] | None, int]:
    for i, n in enumerate(nodes):
        if n.id == node_id:
            return n, parent, nodes, i
        found = _find_node_and_parent(n.children, node_id, n)
        if found[0] is not None:
            return found
    return None, None, None, -1


def update_node(pid: str, node_id: str, patch: dict[str, Any]) -> OutlineNode | None:
    with _lock(pid):
        outline = load(pid)
        if outline is None:
            return None
        node, _parent, _siblings, _idx = _find_node_and_parent(outline.root_sections, node_id)
        if node is None:
            return None
        allowed = {"title", "notes", "stat_refs", "literature_refs", "status", "stat_hints"}
        updates = {k: v for k, v in patch.items() if k in allowed}
        # Apply in place (mutate the model dict tree)
        new_outline = _patch_outline(outline, node_id, updates)
        new_outline.updated_at = _now()
        save(new_outline)
        return new_outline.find(node_id)


def _patch_outline(outline: Outline, node_id: str, updates: dict[str, Any]) -> Outline:
    def _walk(n: OutlineNode) -> OutlineNode:
        if n.id == node_id:
            return n.model_copy(update=updates)
        if not n.children:
            return n
        return n.model_copy(update={"children": [_walk(c) for c in n.children]})

    return outline.model_copy(update={
        "root_sections": [_walk(s) for s in outline.root_sections],
    })


def add_child(pid: str, parent_id: str, title: str,
              *, notes: str = "", stat_hints: list[str] | None = None) -> OutlineNode | None:
    with _lock(pid):
        outline = load(pid)
        if outline is None:
            return None
        parent = outline.find(parent_id)
        if parent is None:
            return None
        new_id = f"{parent_id}.{len(parent.children) + 1}.{uuid.uuid4().hex[:4]}"
        child = OutlineNode(
            id=new_id, title=title,
            level=min(parent.level + 1, 6),
            notes=notes,
            stat_hints=stat_hints or [],
            project_specific=True,
        )

        def _walk(n: OutlineNode) -> OutlineNode:
            if n.id == parent_id:
                return n.model_copy(update={"children": list(n.children) + [child]})
            if not n.children:
                return n
            return n.model_copy(update={"children": [_walk(c) for c in n.children]})

        new_outline = outline.model_copy(update={
            "root_sections": [_walk(s) for s in outline.root_sections],
            "updated_at": _now(),
        })
        save(new_outline)
        return new_outline.find(new_id)


def delete_node(pid: str, node_id: str) -> bool:
    with _lock(pid):
        outline = load(pid)
        if outline is None:
            return False

        removed: list[bool] = [False]

        def _filter(nodes: list[OutlineNode]) -> list[OutlineNode]:
            out: list[OutlineNode] = []
            for n in nodes:
                if n.id == node_id:
                    removed[0] = True
                    continue
                out.append(n.model_copy(update={"children": _filter(n.children)}))
            return out

        new_outline = outline.model_copy(update={
            "root_sections": _filter(outline.root_sections),
            "updated_at": _now(),
        })
        if not removed[0]:
            return False
        save(new_outline)
        return True
