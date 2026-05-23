"""Normalized long-task event payloads for the frontend.

The websocket stream historically emits domain-specific event names such as
``writer.section_done`` and ``export.html.progress``.  The UI can still listen
to those legacy events, but this module provides one stable companion shape
under ``task.event`` so progress overlays do not need to learn every producer.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel


TaskStatus = Literal["queued", "running", "done", "error", "cancelled"]


class TaskEventDTO(BaseModel):
    task_id: str
    kind: str
    status: TaskStatus
    phase: str
    label: str
    progress: int | None = None
    cancellable: bool = False
    node_id: str | None = None
    href: str | None = None
    severity: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pct(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return max(0, min(100, int(float(value))))
    except Exception:
        return default


def _section_progress(payload: dict[str, Any], fallback: int) -> int:
    idx = payload.get("index")
    total = payload.get("total")
    try:
        if total:
            return max(1, min(95, int((float(idx or 0) / max(1.0, float(total))) * 100)))
    except Exception:
        pass
    return fallback


def normalize_task_event(
    project_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> TaskEventDTO | None:
    p = payload or {}

    if event_type.startswith("writer."):
        node_id = str(p.get("node_id") or "") or None
        base = {
            "task_id": f"{project_id}:writer",
            "kind": "writer",
            "label": "Writing report",
            "node_id": node_id,
            "href": f"/p/{project_id}/report?node={node_id}&panel=status" if node_id else f"/p/{project_id}/report?panel=status",
            "cancellable": False,
        }
        if event_type in {"writer.batch_start", "writer.section_start"}:
            return TaskEventDTO(
                **base, status="running", phase=str(node_id or p.get("phase") or "writing"),
                progress=_section_progress(p, 10), started_at=str(p.get("started_at") or _now()),
            )
        if event_type == "writer.section_done":
            return TaskEventDTO(
                **base, status="running", phase=str(node_id or "section done"),
                progress=_section_progress(p, 80),
            )
        if event_type in {"writer.report_done", "writer.batch_done"}:
            return TaskEventDTO(
                **base, status="done", phase="done", progress=100,
                finished_at=str(p.get("finished_at") or _now()),
            )
        if event_type in {"writer.section_error", "writer.report_error"}:
            return TaskEventDTO(
                **base, status="error", phase="error", progress=100, severity="error",
                error=str(p.get("error") or p.get("msg") or "writer failed"),
                finished_at=str(p.get("finished_at") or _now()),
            )

    if event_type.startswith("analysis."):
        status = "running"
        progress = 25
        if event_type.endswith(".done"):
            status, progress = "done", 100
        elif event_type.endswith(".error"):
            status, progress = "error", 100
        return TaskEventDTO(
            task_id=f"{project_id}:analysis",
            kind="analysis",
            status=status,  # type: ignore[arg-type]
            phase=str(p.get("phase") or p.get("mode") or event_type.rsplit(".", 1)[-1]),
            label="Clinical analysis",
            progress=_pct(p.get("percent"), progress),
            cancellable=False,
            href=f"/p/{project_id}/analyze",
            severity="error" if status == "error" else None,
            error=str(p.get("error") or "") or None,
            started_at=str(p.get("started_at") or _now()) if status == "running" else None,
            finished_at=str(p.get("finished_at") or _now()) if status in {"done", "error"} else None,
        )

    if event_type in {"cleansing.applying", "cleansing.apply_done"}:
        done = event_type.endswith("done")
        return TaskEventDTO(
            task_id=f"{project_id}:cleansing",
            kind="cleansing",
            status="done" if done else "running",
            phase="done" if done else str(p.get("file_id") or "applying rules"),
            label="Applying cleansing",
            progress=100 if done else 50,
            cancellable=False,
            href=f"/p/{project_id}/cleanse",
            finished_at=_now() if done else None,
        )

    if event_type.startswith("ingest.") or event_type.startswith("worker."):
        done = event_type.endswith("done") or event_type.endswith("all_done")
        error = event_type.endswith("error")
        return TaskEventDTO(
            task_id=f"{project_id}:ingest",
            kind="ingest",
            status="error" if error else "done" if done else "running",
            phase=str(p.get("worker") or p.get("ingest_type") or p.get("message") or event_type),
            label="Parsing uploads",
            progress=100 if done or error else 30,
            cancellable=False,
            href=f"/p/{project_id}/intake",
            severity="error" if error else None,
            error=str(p.get("error") or "") or None,
            finished_at=_now() if done or error else None,
        )

    if event_type.startswith("router."):
        done = event_type.endswith("all_done")
        error = event_type.endswith("error")
        return TaskEventDTO(
            task_id=f"{project_id}:ingest",
            kind="ingest",
            status="error" if error else "done" if done else "running",
            phase=str(p.get("message") or p.get("file_id") or event_type.rsplit(".", 1)[-1]),
            label="Routing uploads",
            progress=100 if done or error else 20,
            cancellable=False,
            href=f"/p/{project_id}/intake",
            severity="error" if error else None,
            error=str(p.get("error") or "") or None,
            finished_at=_now() if done or error else None,
        )

    if event_type.startswith("tlf."):
        stage = event_type.rsplit(".", 1)[-1]
        return TaskEventDTO(
            task_id=str(p.get("task_id") or f"{project_id}:tlf"),
            kind="tlf",
            status="error" if stage == "error" else "done" if stage == "done" else "running",
            phase=str(p.get("phase") or stage),
            label="Packaging TLF",
            progress=_pct(p.get("percent"), 100 if stage in {"done", "error"} else 30),
            cancellable=bool(p.get("cancellable", False)),
            href=f"/p/{project_id}/export",
            severity="error" if stage == "error" else None,
            error=str(p.get("error") or "") or None,
            started_at=str(p.get("started_at") or _now()) if stage == "start" else None,
            finished_at=str(p.get("finished_at") or _now()) if stage in {"done", "error"} else None,
        )

    fmt_match = re.match(r"^export(?:\.(pdf|html|pptx|md_bundle))?\.(start|progress|done|error)$", event_type)
    if fmt_match:
        fmt = fmt_match.group(1) or "docx"
        stage = fmt_match.group(2)
        return TaskEventDTO(
            task_id=str(p.get("task_id") or f"{project_id}:export:{fmt}"),
            kind=f"export.{fmt}",
            status="error" if stage == "error" else "done" if stage == "done" else "running",
            phase=str(p.get("phase") or stage),
            label=f"Export {fmt.upper() if fmt != 'md_bundle' else 'Markdown bundle'}",
            progress=_pct(p.get("percent"), 100 if stage in {"done", "error"} else 10 if stage == "start" else 50),
            cancellable=bool(p.get("cancellable", False)),
            href=f"/p/{project_id}/export",
            severity="error" if stage == "error" else None,
            error=str(p.get("error") or "") or None,
            started_at=str(p.get("started_at") or _now()) if stage == "start" else None,
            finished_at=str(p.get("finished_at") or _now()) if stage in {"done", "error"} else None,
        )

    if event_type.startswith("multi_review.") or event_type.startswith("review."):
        done = event_type.endswith(".done")
        error = event_type.endswith(".error")
        return TaskEventDTO(
            task_id=f"{project_id}:review",
            kind="review",
            status="error" if error else "done" if done else "running",
            phase=str(p.get("phase") or event_type.rsplit(".", 1)[-1]),
            label="Running review",
            progress=100 if done or error else 20,
            cancellable=False,
            href=f"/p/{project_id}/review",
            severity="error" if error else None,
            error=str(p.get("error") or "") or None,
            finished_at=_now() if done or error else None,
        )

    if event_type.startswith("task."):
        tid = str(p.get("id") or p.get("task_id") or f"{project_id}:task")
        status = "done" if event_type.endswith("deleted") else "running"
        return TaskEventDTO(
            task_id=tid,
            kind="task",
            status=status,  # type: ignore[arg-type]
            phase=str(p.get("status") or event_type.rsplit(".", 1)[-1]),
            label="Task updated",
            progress=100 if status == "done" else 50,
            cancellable=False,
            node_id=str(p.get("node_id") or "") or None,
            href=f"/p/{project_id}/tasks",
            severity=str(p.get("severity") or "") or None,
        )

    return None
