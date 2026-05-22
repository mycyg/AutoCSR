"""In-memory writer status registry.

Holds per-project ReportStatus snapshots while orchestrator/harmonizer are
running. Survives across HTTP requests but **not** across process restarts —
on cold start we rebuild from persisted SectionDraft files via the
``rebuild_from_disk`` helper.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.schemas.report import ReportStatus, WriterTokens

_REGISTRY: dict[str, ReportStatus] = {}
_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get(pid: str) -> ReportStatus | None:
    with _LOCK:
        s = _REGISTRY.get(pid)
        if s is None:
            return None
        # return a deep copy so callers cannot mutate the registry by accident
        return ReportStatus.model_validate(s.model_dump())


def init(pid: str, outline_version: int, leaves_total: int) -> ReportStatus:
    with _LOCK:
        s = ReportStatus(
            project_id=pid,
            outline_version=outline_version,
            leaves_total=leaves_total,
            leaves_done=0,
            leaves_errored=0,
            current_phase="background",
            harmonized=False,
            total_tokens=WriterTokens(),
            total_words=0,
            last_event_at=_now(),
        )
        _REGISTRY[pid] = s
        return s.model_copy()


def update(pid: str, **fields: Any) -> ReportStatus | None:
    with _LOCK:
        s = _REGISTRY.get(pid)
        if s is None:
            return None
        new = s.model_copy(update={**fields, "last_event_at": _now()})
        _REGISTRY[pid] = new
        return new.model_copy()


def add_section(pid: str, node_id: str, title: str, *, status: str,
                words: int = 0, error: str | None = None,
                tokens_in: int = 0, tokens_out: int = 0) -> None:
    with _LOCK:
        s = _REGISTRY.get(pid)
        if s is None:
            return
        sections = [dict(x) for x in s.sections if x.get("node_id") != node_id]
        entry: dict[str, Any] = {"node_id": node_id, "title": title, "status": status, "words": words}
        if error:
            entry["error"] = error
        sections.append(entry)
        leaves_done = sum(1 for x in sections if x.get("status") == "done")
        leaves_errored = sum(1 for x in sections if x.get("status") == "error")
        new_tokens = WriterTokens(
            input=s.total_tokens.input + tokens_in,
            output=s.total_tokens.output + tokens_out,
        )
        new = s.model_copy(update={
            "sections": sections,
            "leaves_done": leaves_done,
            "leaves_errored": leaves_errored,
            "total_tokens": new_tokens,
            "total_words": s.total_words + words,
            "last_event_at": _now(),
        })
        _REGISTRY[pid] = new


def mark_error(pid: str, error: str) -> None:
    with _LOCK:
        s = _REGISTRY.get(pid)
        if s is None:
            return
        _REGISTRY[pid] = s.model_copy(update={
            "current_phase": "error", "error": error, "last_event_at": _now(),
        })


def reset(pid: str) -> None:
    with _LOCK:
        _REGISTRY.pop(pid, None)
