"""Comment schemas (M11 — collaborative review).

Comments are inline annotations attached to a section + paragraph + char
range. They live in their own JSONL file so creation / deletion stays
append-only and parallel-safe:

    data/projects/<pid>/comments.jsonl

Status workflow:
    open      — needs attention
    resolved  — addressed (manually or via batch apply)
    rejected  — explicitly dismissed (no change needed)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


CommentStatus = Literal["open", "resolved", "rejected"]


class Comment(BaseModel):
    id: str
    project_id: str
    node_id: str
    paragraph_idx: int = 0
    char_range: tuple[int, int] = (0, 0)
    author: str = "user"
    body: str = ""
    status: CommentStatus = "open"
    created_at: datetime
    applied_in_draft_version: int | None = None    # populated by apply_all_unresolved


class CommentApplyResult(BaseModel):
    """Summary returned by /comments/apply."""
    project_id: str
    applied_count: int = 0
    skipped_count: int = 0
    new_versions: dict[str, int] = Field(default_factory=dict)   # node_id -> new draft version
    warnings: list[str] = Field(default_factory=list)
