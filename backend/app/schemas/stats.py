"""Statistical analysis schemas — StatBlock + run params.

A StatBlock is the unit of analysis output that downstream writer agents consume.
It carries both the structured result (`result_json`) for programmatic use and
the rendered `markdown_table` for prose citation.

Ref codes (see app/corpus/index.py):
    Ref<stat_id>            — whole block
    Ref<stat_id>.var<col>   — specific variable inside the block
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AnalysisType = Literal["descriptive", "inferential", "survival", "safety"]


class StatBlock(BaseModel):
    id: str
    project_id: str
    analysis_type: AnalysisType
    title: str
    params: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] = Field(default_factory=dict)
    markdown_table: str = ""
    source_files: list[str] = Field(default_factory=list)
    created_at: datetime
    ref_code: str = ""           # populated at save time
    notes: list[str] = Field(default_factory=list)


class StatBlockSummary(BaseModel):
    """Lightweight index entry — fast list views."""
    id: str
    project_id: str
    analysis_type: AnalysisType
    title: str
    source_files: list[str] = Field(default_factory=list)
    created_at: datetime
    ref_code: str = ""
    n_rows: int | None = None   # optional shape hint shown in UI
    n_cols: int | None = None
