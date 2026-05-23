"""Project workbench and cross-project search aggregation.

These endpoints are intentionally thin read models over existing per-project
stores.  They avoid a migration while giving the frontend one stable place to
render the modern project landing page and global command-search experience.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.middleware import get_current_user
from app.auth.models import User
from app.config import data_dir
from app.projects.manager import ensure_project_access

router = APIRouter(tags=["projects"])


STEP_ORDER = ["intake", "cleanse", "analyze", "outline", "report", "review", "tasks", "export"]
STEP_PATHS = {
    "intake": "intake",
    "cleanse": "cleanse",
    "analyze": "analyze",
    "outline": "outline",
    "report": "report",
    "review": "review",
    "tasks": "tasks",
    "export": "export",
}


def _pdir(pid: str):
    p = data_dir() / "projects" / pid
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    return p


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _contains(term: str, *values: Any) -> bool:
    if not term:
        return True
    hay = "\n".join(str(v or "") for v in values).lower()
    return term.lower() in hay


def _review_issues(pid: str) -> list[dict[str, Any]]:
    try:
        from app.agents.reviewer_agent import load_latest
        latest = load_latest(pid)
        if latest is None:
            return []
        return [i.model_dump() for i in latest.issues]
    except Exception:
        return []


def _hallucination_count(pid: str) -> int:
    try:
        from app.safety.hallucination_guard import project_scan
        return len(project_scan(pid))
    except Exception:
        return 0


def _state_summary(pid: str) -> dict[str, Any]:
    try:
        from app.server.routes.projects import state_summary
        return state_summary(pid)
    except Exception:
        return {"steps": {}, "current_step": "intake"}


def _next_action(pid: str, state: dict[str, Any]) -> dict[str, Any]:
    current = str(state.get("current_step") or "intake")
    if current not in STEP_ORDER:
        current = "intake"
    label = {
        "intake": "Upload source data",
        "cleanse": "Review cleansing proposals",
        "analyze": "Run clinical analyses",
        "outline": "Build the CSR outline",
        "report": "Draft report sections",
        "review": "Run review checks",
        "tasks": "Resolve review tasks",
        "export": "Export the CSR",
    }.get(current, "Continue workflow")
    return {
        "step": current,
        "label": label,
        "href": f"/p/{pid}/{STEP_PATHS[current]}",
    }


def _recent_activity(pid: str, limit: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from app.export.docx_builder import list_exports
        for item in list_exports(pid)[:limit]:
            out.append({
                "kind": "export",
                "label": f"Exported {item.get('filename')}",
                "ts": item.get("created_at"),
                "href": f"/p/{pid}/export",
            })
    except Exception:
        pass
    try:
        from app.collab.tasks import list_tasks
        for task in list_tasks(pid)[:limit]:
            out.append({
                "kind": "task",
                "label": task.title or task.body[:80],
                "ts": task.updated_at.isoformat() if hasattr(task.updated_at, "isoformat") else str(task.updated_at),
                "href": f"/p/{pid}/tasks",
                "severity": task.severity,
            })
    except Exception:
        pass
    try:
        from app.report.store import list_drafts
        for draft in list_drafts(pid)[:limit]:
            out.append({
                "kind": "draft",
                "label": f"{draft.node_id} {draft.title}",
                "ts": draft.generated_at.isoformat() if draft.generated_at else None,
                "href": f"/p/{pid}/report?node={draft.node_id}&panel=reader",
            })
    except Exception:
        pass
    out.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    return out[:limit]


@router.get("/projects/{pid}/workbench")
def get_workbench(pid: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    project = ensure_project_access(user, pid, "read")
    _pdir(pid)
    state = _state_summary(pid)

    try:
        from app.ingestion.orchestrator import load_entries
        files = load_entries(pid)
    except Exception:
        files = []
    try:
        from app.analysis.store import list_blocks
        stats = list_blocks(pid)
    except Exception:
        stats = []
    try:
        from app.report.store import list_drafts
        drafts = list_drafts(pid)
    except Exception:
        drafts = []
    try:
        from app.collab.tasks import list_tasks
        tasks = list_tasks(pid)
    except Exception:
        tasks = []
    try:
        from app.export.docx_builder import list_exports
        exports = list_exports(pid)
    except Exception:
        exports = []

    issues = _review_issues(pid)
    open_tasks = [t for t in tasks if getattr(t, "status", "") in {"open", "in_progress"}]
    risk_counts = {
        "error": sum(1 for i in issues if i.get("severity") == "error" and not i.get("ignored")),
        "warn": sum(1 for i in issues if i.get("severity") == "warn" and not i.get("ignored")),
        "info": sum(1 for i in issues if i.get("severity") == "info" and not i.get("ignored")),
        "hallucination": _hallucination_count(pid),
    }

    return {
        "project": {
            "id": pid,
            "name": project.get("name") or pid,
            "status": project.get("status") or "draft",
            "principle_id": project.get("principle_id"),
            "language": project.get("language") or "zh",
            "tags": project.get("tags") or [],
            "last_opened_at": project.get("last_opened_at"),
        },
        "steps": state.get("steps") or {},
        "current_step": state.get("current_step") or "intake",
        "next_action": _next_action(pid, state),
        "metrics": {
            "files": len(files or []),
            "stats": len(stats or []),
            "drafts": len(drafts or []),
            "open_tasks": len(open_tasks),
            "exports": len(exports or []),
            "review_issues": sum(risk_counts[k] for k in ("error", "warn", "info")),
        },
        "risks": risk_counts,
        "tasks": [
            {
                "id": t.id,
                "title": t.title or t.body[:80],
                "status": t.status,
                "severity": t.severity,
                "assignee": t.assignee,
                "node_id": t.node_id,
                "href": f"/p/{pid}/report?node={t.node_id}&panel=comments&highlight={t.id}" if t.node_id else f"/p/{pid}/tasks",
                "updated_at": t.updated_at.isoformat() if hasattr(t.updated_at, "isoformat") else str(t.updated_at),
            }
            for t in open_tasks[:6]
        ],
        "exports": exports[:5],
        "activity": _recent_activity(pid),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/projects/{pid}/search")
def project_search(
    pid: str,
    q: str = Query(default=""),
    types: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ensure_project_access(user, pid, "read")
    _pdir(pid)
    wanted = {t.strip() for t in (types or "").split(",") if t.strip()}

    def allow(kind: str) -> bool:
        return not wanted or kind in wanted

    term = q.strip()
    hits: list[dict[str, Any]] = []

    if allow("section"):
        try:
            from app.outline.store import load as load_outline
            outline = load_outline(pid)
            if outline is not None:
                for node in outline.walk():
                    if _contains(term, node.id, node.title, node.notes):
                        hits.append({
                            "id": f"section:{node.id}",
                            "type": "section",
                            "title": f"{node.id} {node.title}",
                            "snippet": node.notes or "Outline section",
                            "href": f"/p/{pid}/report?node={node.id}&panel=reader",
                            "node_id": node.id,
                        })
        except Exception:
            pass

    if allow("draft"):
        try:
            from app.report.store import list_drafts
            for draft in list_drafts(pid):
                if _contains(term, draft.node_id, draft.title, draft.markdown):
                    snippet = (draft.markdown or "").replace("\n", " ").strip()[:180]
                    hits.append({
                        "id": f"draft:{draft.node_id}",
                        "type": "draft",
                        "title": draft.title or draft.node_id,
                        "snippet": snippet or "Section draft",
                        "href": f"/p/{pid}/report?node={draft.node_id}&panel=reader",
                        "node_id": draft.node_id,
                        "severity": "warn" if draft.warnings else None,
                    })
        except Exception:
            pass

    if allow("stat"):
        try:
            from app.analysis.store import list_blocks
            for stat in list_blocks(pid):
                if _contains(term, stat.get("id"), stat.get("title"), stat.get("analysis_type"), stat.get("ref_code")):
                    hits.append({
                        "id": f"stat:{stat.get('id')}",
                        "type": "stat",
                        "title": str(stat.get("title") or stat.get("id")),
                        "snippet": f"{stat.get('analysis_type') or 'analysis'} · {stat.get('ref_code') or ''}",
                        "href": f"/p/{pid}/analyze?stat={stat.get('id')}",
                    })
        except Exception:
            pass

    if allow("task"):
        try:
            from app.collab.tasks import list_tasks
            for task in list_tasks(pid):
                if _contains(term, task.id, task.title, task.body, task.node_id, task.assignee):
                    hits.append({
                        "id": f"task:{task.id}",
                        "type": "task",
                        "title": task.title or task.body[:80] or task.id,
                        "snippet": f"{task.status} · @{task.assignee}",
                        "href": f"/p/{pid}/report?node={task.node_id}&panel=comments&highlight={task.id}" if task.node_id else f"/p/{pid}/tasks?highlight={task.id}",
                        "node_id": task.node_id,
                        "severity": task.severity,
                    })
        except Exception:
            pass

    if allow("review"):
        for issue in _review_issues(pid):
            loc = issue.get("location") or {}
            node_id = loc.get("node_id")
            if _contains(term, issue.get("id"), issue.get("message"), issue.get("suggestion"), node_id, issue.get("checker")):
                hits.append({
                    "id": f"review:{issue.get('id')}",
                    "type": "review",
                    "title": issue.get("message") or issue.get("id"),
                    "snippet": issue.get("suggestion") or issue.get("checker") or "Review issue",
                    "href": f"/p/{pid}/report?node={node_id}&panel=comments&highlight={issue.get('id')}" if node_id else f"/p/{pid}/review",
                    "node_id": node_id,
                    "severity": issue.get("severity"),
                })

    if allow("export"):
        try:
            from app.export.docx_builder import list_exports
            for item in list_exports(pid):
                if _contains(term, item.get("filename"), item.get("created_at")):
                    hits.append({
                        "id": f"export:{item.get('filename')}",
                        "type": "export",
                        "title": str(item.get("filename") or "Export"),
                        "snippet": f"{_safe_int(item.get('size_bytes')) // 1024} KB · {item.get('created_at') or ''}",
                        "href": f"/p/{pid}/export",
                    })
        except Exception:
            pass

    # Stable, useful ordering: exact-ish title matches first, then severity,
    # then original store order.
    def _rank(hit: dict[str, Any]) -> tuple[int, int]:
        title = str(hit.get("title") or "").lower()
        exact = 0 if term and term.lower() in title else 1
        sev = {"error": 0, "warn": 1, "info": 2}.get(str(hit.get("severity") or ""), 3)
        return exact, sev

    hits.sort(key=_rank)
    return hits[:limit]

