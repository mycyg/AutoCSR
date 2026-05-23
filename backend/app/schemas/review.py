"""Review schemas (M10 — reviewer agent).

The reviewer agent runs three parallel checkers (ICH E3 structure,
numeric consistency, citation validity) and aggregates their findings
into a single ReviewResult. Each Issue is severity-tagged and may carry
a structured location (node + char range) so the frontend can offer a
"jump to issue" button.

A project may accumulate many ReviewResult snapshots (rerun after each
fix); ``ignored_issue_ids`` survives across snapshots so the user does
not have to re-dismiss the same false positive.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["error", "warn", "info"]


class IssueLocation(BaseModel):
    """Pointer back to where an issue lives in the report.

    All fields optional — checkers populate what they can. ``char_range``
    is ``(start, end)`` byte offsets into the section's markdown body.
    """
    node_id: str | None = None
    char_range: tuple[int, int] | None = None
    extra: dict[str, str] = Field(default_factory=dict)


class Issue(BaseModel):
    """One reviewer finding."""
    id: str
    severity: Severity = "warn"
    location: IssueLocation = Field(default_factory=IssueLocation)
    message: str = ""
    suggestion: str = ""
    checker: str = ""               # short name of the checker that emitted this
    ignored: bool = False


class CheckerStatus(BaseModel):
    """Per-checker status snapshot (so the UI can render per-checker
    progress and surface checker-level failures without losing other
    checkers' issues)."""
    name: str
    ok: bool = True
    issues_count: int = 0
    error: str | None = None
    duration_ms: int = 0


class ReviewResult(BaseModel):
    project_id: str
    passed: bool = False
    issues: list[Issue] = Field(default_factory=list)
    checkers: list[CheckerStatus] = Field(default_factory=list)
    created_at: datetime
    ignored_issue_ids: list[str] = Field(default_factory=list)


class ReviewHistoryEntry(BaseModel):
    """Lightweight summary surfaced in /review/history."""
    created_at: datetime
    passed: bool
    n_errors: int
    n_warns: int
    n_infos: int
