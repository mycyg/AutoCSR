"""Project CRUD — M1 surface + M12 enhancements.

Storage: a single JSON file `<data_dir>/projects.json` holding a list of
serialized Project records. Per-project artefacts live under
`<data_dir>/projects/<pid>/{raw,processed,corpus,chapters,exports,chats}`.

M12 additions:
  * search / tag-filter / archive-filter / sort on GET /projects
  * PATCH /projects/{pid}    — rename, tags, archived, notes, language
  * DELETE /projects/{pid}   — only for archived (safety)
  * POST /projects/from_template/{template_id}  — clone a preset
  * GET /api/templates       — list templates
  * GET /projects/{pid}/state_summary — per-step counters for the UI
  * last_opened_at auto-touched on every GET /projects/{pid}
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.config import data_dir
from app.projects.templates import get_template, list_templates
from app.schemas.project import Project, ProjectCreate, ProjectUpdate

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


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    """Back-fill M12 fields on historical records so the API surface is
    uniform regardless of when the project was created."""
    item.setdefault("tags", [])
    item.setdefault("archived", False)
    item.setdefault("last_opened_at", None)
    item.setdefault("language", "zh")
    item.setdefault("notes", None)
    item.setdefault("template_id", None)
    return item


def _touch_last_opened(pid: str) -> None:
    with _LOCK:
        items = _load_all()
        changed = False
        for it in items:
            if it.get("id") == pid:
                it["last_opened_at"] = datetime.now(timezone.utc).isoformat()
                changed = True
                break
        if changed:
            _save_all(items)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


@router.get("/templates")
def list_templates_endpoint() -> list[dict[str, Any]]:
    return [json.loads(t.model_dump_json()) for t in list_templates()]


@router.post("/projects/from_template/{template_id}", status_code=201)
def create_from_template(template_id: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    tpl = get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail=f"template {template_id} not found")
    name = (body.get("name") or tpl.name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="project name is required")
    pid = uuid.uuid4().hex[:12]
    proj = Project(
        id=pid,
        name=name,
        principle_id=tpl.principle_id,
        created_at=datetime.now(timezone.utc),
        status="draft",
        tags=list(tpl.tags or []),
        archived=False,
        last_opened_at=None,
        language=tpl.language or "zh",
        notes=tpl.notes,
        template_id=tpl.id,
    )
    with _LOCK:
        items = _load_all()
        items.append(json.loads(proj.model_dump_json()))
        _save_all(items)
    pdir = _project_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pdir / sub).mkdir(exist_ok=True)
    try:
        from app.state import default_machine
        default_machine.get_record(pid)
    except Exception:
        pass
    return json.loads(proj.model_dump_json())


# ---------------------------------------------------------------------------
# Standard CRUD
# ---------------------------------------------------------------------------


@router.get("/projects")
def list_projects(
    search: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    sort: str = Query(default="last_opened"),
) -> list[dict[str, Any]]:
    with _LOCK:
        items = [_normalize(dict(it)) for it in _load_all()]
    # Filter
    if search:
        s_lc = search.lower()
        items = [it for it in items if s_lc in str(it.get("name", "")).lower()
                  or s_lc in str(it.get("id", "")).lower()
                  or any(s_lc in str(t).lower() for t in (it.get("tags") or []))]
    if tag:
        t_lc = tag.lower()
        items = [it for it in items if any(t_lc == str(x).lower() for x in (it.get("tags") or []))]
    if archived is not None:
        items = [it for it in items if bool(it.get("archived")) == archived]
    # Sort
    def _key_last_opened(it: dict[str, Any]) -> str:
        return str(it.get("last_opened_at") or it.get("created_at") or "")
    def _key_created(it: dict[str, Any]) -> str:
        return str(it.get("created_at") or "")
    def _key_name(it: dict[str, Any]) -> str:
        return str(it.get("name") or "").lower()
    if sort == "name":
        items.sort(key=_key_name)
    elif sort == "created":
        items.sort(key=_key_created, reverse=True)
    else:  # default last_opened
        items.sort(key=_key_last_opened, reverse=True)
    return items


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict[str, Any]:
    pid = uuid.uuid4().hex[:12]
    proj = Project(
        id=pid,
        name=body.name.strip(),
        principle_id=body.principle_id,
        created_at=datetime.now(timezone.utc),
        status="draft",
        language=(body.language or "zh"),
        notes=body.notes,
        template_id=body.template_id,
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
    # Initialize state machine record (idempotent)
    try:
        from app.state import default_machine
        default_machine.get_record(pid)
    except Exception:
        pass
    return json.loads(proj.model_dump_json())


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict[str, Any]:
    with _LOCK:
        for item in _load_all():
            if item.get("id") == pid:
                # Touch last_opened_at as a side effect of "opening".
                _touch_last_opened(pid)
                # Reload to surface the new last_opened value.
                for refreshed in _load_all():
                    if refreshed.get("id") == pid:
                        return _normalize(dict(refreshed))
                return _normalize(dict(item))
    raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.patch("/projects/{pid}")
def update_project(pid: str, body: ProjectUpdate) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    with _LOCK:
        items = _load_all()
        for it in items:
            if it.get("id") != pid:
                continue
            for k, v in patch.items():
                it[k] = v
            _save_all(items)
            return _normalize(dict(it))
    raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.delete("/projects/{pid}")
def delete_project(pid: str, force: bool = Query(default=False)) -> dict[str, Any]:
    with _LOCK:
        items = _load_all()
        target = next((it for it in items if it.get("id") == pid), None)
        if target is None:
            raise HTTPException(status_code=404, detail=f"project {pid} not found")
        if not bool(target.get("archived")) and not force:
            raise HTTPException(
                status_code=409,
                detail="project must be archived first; pass ?force=true to override",
            )
        items = [it for it in items if it.get("id") != pid]
        _save_all(items)
    # Drop the per-project artefacts; best-effort, never crash the request.
    try:
        shutil.rmtree(_project_dir(pid), ignore_errors=True)
    except Exception:
        pass
    return {"ok": True, "id": pid}


# ---------------------------------------------------------------------------
# Step state summary (drives the navbar badges)
# ---------------------------------------------------------------------------


def _safe_count(callable_, *args, default: int = 0, **kwargs) -> int:
    try:
        v = callable_(*args, **kwargs)
        if hasattr(v, "__len__"):
            return len(v)
        if isinstance(v, int):
            return v
    except Exception:
        pass
    return default


@router.get("/projects/{pid}/state_summary")
def state_summary(pid: str) -> dict[str, Any]:
    """Per-step counters for the navbar. Each step returns
    ``{pending, done, error, info}`` (any subset may be 0)."""
    pdir = _project_dir(pid)
    if not pdir.exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    summary: dict[str, Any] = {
        "intake": {"done": 0, "pending": 0, "error": 0},
        "cleanse": {"done": 0, "pending": 0, "error": 0},
        "analyze": {"done": 0, "pending": 0},
        "outline": {"done": 0},
        "report": {"done": 0, "pending": 0, "error": 0},
        "review": {"done": 0, "error": 0, "info": 0},
        "export": {"done": 0},
    }
    # ---- intake: file count from ingest store --------------------------------
    try:
        from app.ingestion.orchestrator import load_entries
        entries = load_entries(pid)
        for e in entries or []:
            s = str(getattr(e, "status", "") or "")
            if s == "done":
                summary["intake"]["done"] += 1
            elif s == "error":
                summary["intake"]["error"] += 1
            else:
                summary["intake"]["pending"] += 1
    except Exception:
        pass
    # ---- cleanse: proposal counts -------------------------------------------
    try:
        from app.cleansing.pipeline_io import load_proposals
        props = load_proposals(pid)
        for p in props or []:
            s = str(getattr(p, "status", "") or "")
            if s in ("accepted", "applied"):
                summary["cleanse"]["done"] += 1
            elif s == "rejected":
                pass
            else:
                summary["cleanse"]["pending"] += 1
    except Exception:
        pass
    # ---- analyze: stat blocks -----------------------------------------------
    try:
        from app.analysis.store import list_blocks
        summary["analyze"]["done"] = len(list_blocks(pid) or [])
    except Exception:
        pass
    # ---- outline ------------------------------------------------------------
    try:
        from app.outline.store import load as load_outline
        outline = load_outline(pid)
        if outline is not None:
            def _walk(n):
                total = 1
                for c in (n.children or []):
                    total += _walk(c)
                return total
            n = sum(_walk(root) for root in (outline.root_sections or []))
            summary["outline"]["done"] = n
    except Exception:
        pass
    # ---- report: drafts -----------------------------------------------------
    try:
        from app.report.store import list_drafts
        drafts = list_drafts(pid) or []
        for d in drafts:
            s = str(getattr(d, "status", "") or "")
            md = getattr(d, "markdown", "") or ""
            if s == "error":
                summary["report"]["error"] += 1
            elif s in ("draft", "harmonized") and md.strip():
                summary["report"]["done"] += 1
            else:
                summary["report"]["pending"] += 1
    except Exception:
        pass
    # ---- review issues ------------------------------------------------------
    try:
        review_dir = pdir / "reviews"
        if review_dir.exists():
            files = sorted([f for f in review_dir.glob("*.json")
                              if not f.name.startswith("_")])
            if files:
                last = files[-1]
                data = json.loads(last.read_text(encoding="utf-8"))
                for it in (data.get("issues") or []):
                    sev = str(it.get("severity") or "info")
                    if sev == "error":
                        summary["review"]["error"] += 1
                    elif sev == "warn":
                        summary["review"]["info"] += 1
                    else:
                        summary["review"]["info"] += 1
                summary["review"]["done"] = 1
    except Exception:
        pass
    # ---- export -------------------------------------------------------------
    try:
        from app.export.docx_builder import list_exports
        summary["export"]["done"] = len(list_exports(pid) or [])
    except Exception:
        pass
    # ---- current step heuristic ---------------------------------------------
    current = "intake"
    if summary["intake"]["done"] > 0:
        current = "cleanse"
    if summary["cleanse"]["done"] > 0:
        current = "analyze"
    if summary["analyze"]["done"] > 0:
        current = "outline"
    if summary["outline"]["done"] > 0:
        current = "report"
    if summary["report"]["done"] > 0:
        current = "review"
    if summary["review"]["done"] > 0 or summary["export"]["done"] > 0:
        current = "export"
    return {"steps": summary, "current_step": current}
