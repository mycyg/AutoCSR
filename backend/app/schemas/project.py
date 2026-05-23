"""Project schemas — the root entity in AutoCSR.

M1 keeps this thin. M2+ adds settings, ingest jobs, analyses, outline, chapters.
V2-D (M12) adds optional management fields: ``tags``, ``archived``,
``last_opened_at``, ``language``, ``notes`` and ``template_id``. All are
optional with safe defaults so the historical persisted records on disk
(without these keys) keep validating.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectStatus = Literal["draft", "intake", "cleansing", "analysis", "writing", "exported"]


class ProjectCreate(BaseModel):
    """Request body for POST /projects."""
    name: str = Field(..., min_length=1, max_length=200)
    principle_id: str | None = None
    language: str | None = None  # M12 / M13 — 'zh' default
    notes: str | None = None
    template_id: str | None = None


class ProjectUpdate(BaseModel):
    """PATCH /projects/{pid} body — all fields optional."""
    name: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = None
    archived: bool | None = None
    notes: str | None = None
    language: str | None = None
    principle_id: str | None = None


class Project(BaseModel):
    """Persisted project record (one entry in data/projects.json)."""
    id: str
    name: str
    principle_id: str | None = None
    created_at: datetime
    status: ProjectStatus = "draft"
    # M12 additions — all optional, defaults keep older records valid.
    tags: list[str] = Field(default_factory=list)
    archived: bool = False
    last_opened_at: datetime | None = None
    # M13 additions — language / template provenance.
    language: str = "zh"
    notes: str | None = None
    template_id: str | None = None
