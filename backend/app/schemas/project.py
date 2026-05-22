"""Project schemas — the root entity in AutoCSR.

M1 keeps this thin. M2+ adds settings, ingest jobs, analyses, outline, chapters.
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


class Project(BaseModel):
    """Persisted project record (one entry in data/projects.json)."""
    id: str
    name: str
    principle_id: str | None = None
    created_at: datetime
    status: ProjectStatus = "draft"
