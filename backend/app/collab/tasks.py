"""Review tasks — per-project assignable items (M16).

A task can spawn from a reviewer issue, a comment, or be created
manually. State machine:

    open → in_progress → resolved
                       → wont_fix
                ← reopen ←

Storage: ``data/projects/<pid>/tasks.jsonl``. Tasks are append-only
event-sourced: the latest entry per ``id`` wins.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.config import data_dir

TaskStatus = Literal["open", "in_progress", "resolved", "wont_fix"]
Severity = Literal["error", "warn", "info"]
TaskSource = Literal["manual", "issue", "comment", "multi_review"]


class TaskComment(BaseModel):
    id: str
    author: str = ""
    body: str = ""
    ts: datetime


class ReviewTask(BaseModel):
    id: str
    project_id: str
    node_id: str | None = None
    source: TaskSource = "manual"
    source_ref: str | None = None   # issue_id / comment_id / ...
    assignee: str = ""
    creator: str = ""
    due_date: datetime | None = None
    status: TaskStatus = "open"
    severity: Severity = "warn"
    title: str = ""
    body: str = ""
    comments: list[TaskComment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    # M17 — optional ordered signature chain (see app.collab.sign_chain).
    # Older tasks on disk lack the field; default keeps them loadable.
    sign_chain: list[dict] | None = None


_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


def _path(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "tasks.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# Public alias for sister modules (e.g. sign_chain) that need the raw
# storage path under the same per-project lock semantics.
tasks_path = _path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_all(pid: str) -> dict[str, ReviewTask]:
    p = _path(pid)
    if not p.exists():
        return {}
    out: dict[str, ReviewTask] = {}
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                t = ReviewTask.model_validate_json(line)
            except Exception:
                continue
            out[t.id] = t
    return out


def _append(pid: str, task: ReviewTask) -> None:
    with _path(pid).open("a", encoding="utf-8") as f:
        f.write(task.model_dump_json() + "\n")


def _publish(pid: str, event: str, payload: dict) -> None:
    try:
        from app.server.ws import publish_sync
        publish_sync(pid, event, payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_task(
    pid: str,
    *,
    assignee: str,
    creator: str = "",
    body: str = "",
    title: str = "",
    node_id: str | None = None,
    severity: Severity = "warn",
    source: TaskSource = "manual",
    source_ref: str | None = None,
    due_date: datetime | None = None,
) -> ReviewTask:
    now = _now()
    task = ReviewTask(
        id="task_" + uuid.uuid4().hex[:10],
        project_id=pid,
        node_id=node_id,
        source=source,
        source_ref=source_ref,
        assignee=assignee,
        creator=creator,
        due_date=due_date,
        status="open",
        severity=severity,
        title=title or (body[:60] if body else f"Task {source}"),
        body=body,
        comments=[],
        created_at=now,
        updated_at=now,
    )
    with _plock(pid):
        _append(pid, task)
    _publish(pid, "task.created", {
        "id": task.id, "assignee": assignee, "severity": severity,
        "node_id": node_id, "source": source, "source_ref": source_ref,
    })
    return task


def list_tasks(
    pid: str,
    *,
    assignee: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    node_id: str | None = None,
) -> list[ReviewTask]:
    all_t = list(_read_all(pid).values())
    if assignee:
        all_t = [t for t in all_t if t.assignee == assignee]
    if status:
        all_t = [t for t in all_t if t.status == status]
    if severity:
        all_t = [t for t in all_t if t.severity == severity]
    if node_id:
        all_t = [t for t in all_t if t.node_id == node_id]
    return sorted(all_t, key=lambda t: t.created_at, reverse=True)


def get_task(pid: str, tid: str) -> ReviewTask | None:
    return _read_all(pid).get(tid)


def patch_task(
    pid: str,
    tid: str,
    *,
    status: TaskStatus | None = None,
    assignee: str | None = None,
    body: str | None = None,
    title: str | None = None,
    severity: Severity | None = None,
    add_comment: TaskComment | None = None,
) -> ReviewTask | None:
    with _plock(pid):
        existing = _read_all(pid).get(tid)
        if existing is None:
            return None
        patch: dict = {"updated_at": _now()}
        if status is not None:
            patch["status"] = status
        if assignee is not None:
            patch["assignee"] = assignee
        if body is not None:
            patch["body"] = body
        if title is not None:
            patch["title"] = title
        if severity is not None:
            patch["severity"] = severity
        new_comments = list(existing.comments)
        if add_comment is not None:
            new_comments.append(add_comment)
            patch["comments"] = new_comments
        updated = existing.model_copy(update=patch)
        _append(pid, updated)
    _publish(pid, "task.updated", {
        "id": updated.id, "status": updated.status, "assignee": updated.assignee,
    })
    # If task was source=comment, mirror status onto the comment.
    if status in ("resolved", "wont_fix") and updated.source == "comment" and updated.source_ref:
        try:
            from app.report import comments as comments_mod
            comments_mod.update_comment(pid, updated.source_ref,
                                        status="resolved")
        except Exception:
            pass
    return updated


def resolve_task(pid: str, tid: str, *, by: str = "") -> ReviewTask | None:
    return patch_task(pid, tid, status="resolved")


def reopen_task(pid: str, tid: str) -> ReviewTask | None:
    return patch_task(pid, tid, status="open")


def delete_task(pid: str, tid: str) -> bool:
    """Soft-delete: append a wont_fix tombstone."""
    with _plock(pid):
        existing = _read_all(pid).get(tid)
        if existing is None:
            return False
        tomb = existing.model_copy(update={
            "status": "wont_fix", "updated_at": _now(),
            "body": (existing.body or "") + "\n[deleted]",
        })
        _append(pid, tomb)
    _publish(pid, "task.deleted", {"id": tid})
    return True


# ---------------------------------------------------------------------------
# Spawn helpers
# ---------------------------------------------------------------------------

def from_issue(
    pid: str,
    issue_id: str,
    *,
    assignee: str,
    creator: str = "",
    due_date: datetime | None = None,
) -> ReviewTask | None:
    """Turn a reviewer Issue (M10 or M16 multi-review) into a task.

    We search the latest review snapshot + every multi_reviews entry for
    the matching ``issue_id``.
    """
    issue = _find_issue(pid, issue_id)
    if issue is None:
        return None
    node_id = (issue.get("location") or {}).get("node_id") or None
    sev = issue.get("severity") or "warn"
    body = issue.get("message") or ""
    sug = issue.get("suggestion") or ""
    if sug:
        body = f"{body}\n\n建议: {sug}"
    return create_task(
        pid,
        assignee=assignee, creator=creator,
        body=body, title=(issue.get("message") or "")[:60],
        node_id=node_id,
        severity=sev,
        source="issue", source_ref=issue_id, due_date=due_date,
    )


def from_comment(
    pid: str,
    comment_id: str,
    *,
    assignee: str,
    creator: str = "",
    due_date: datetime | None = None,
) -> ReviewTask | None:
    from app.report import comments as comments_mod
    cm = None
    for c in comments_mod.list_comments(pid):
        if c.id == comment_id:
            cm = c
            break
    if cm is None:
        return None
    return create_task(
        pid, assignee=assignee, creator=creator,
        body=cm.body, title=cm.body[:60], node_id=cm.node_id,
        severity="warn", source="comment", source_ref=comment_id,
        due_date=due_date,
    )


def _find_issue(pid: str, issue_id: str) -> dict | None:
    """Search latest review.json + latest multi_reviews.json."""
    pdir = data_dir() / "projects" / pid
    candidates = []
    rev = pdir / "reviews" / "latest.json"
    if rev.exists():
        candidates.append(rev)
    multi = pdir / "multi_reviews" / "latest.json"
    if multi.exists():
        candidates.append(multi)
    for c in candidates:
        try:
            data = json.loads(c.read_text(encoding="utf-8"))
        except Exception:
            continue
        # multi result contains nested reviewer ReviewResults
        if "issues" in data:
            for iss in data.get("issues") or []:
                if iss.get("id") == issue_id:
                    return iss
        for key in ("statistician", "medical", "regulatory", "completeness"):
            inner = data.get(key) or {}
            for iss in inner.get("issues") or []:
                if iss.get("id") == issue_id:
                    return iss
    return None
