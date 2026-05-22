"""Cleansing workbench schemas — proposals, audit, pipeline.

Proposal type set:
  rename_column / cast_dtype / unit_convert / normalize_value /
  impute_missing / outlier_flag / hash_pii / split_column /
  merge_columns / derive_column / map_to_cdisc (M3+)

`hash_pii` is mandatory by policy: users may tweak parameters but cannot reject.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProposalType = Literal[
    "rename_column", "cast_dtype", "unit_convert", "normalize_value",
    "impute_missing", "outlier_flag", "hash_pii", "split_column",
    "merge_columns", "derive_column", "map_to_cdisc",
]

ProposalStatus = Literal["pending", "accepted", "rejected", "applied", "edited"]


class CleansingProposal(BaseModel):
    id: str
    project_id: str
    file_id: str
    sheet: str | None = None
    type: ProposalType
    target_columns: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    confidence: float = 0.5
    impact_rows: int = 0
    status: ProposalStatus = "pending"
    mandatory: bool = False           # hash_pii sets this to True
    created_at: datetime
    edited_at: datetime | None = None


class AuditLogEntry(BaseModel):
    timestamp: datetime
    project_id: str
    file_id: str
    proposal_id: str | None = None
    action: str          # apply | rollback | edit | reject | accept
    detail: dict[str, Any] = Field(default_factory=dict)
    snapshot_id: str | None = None
    rows_before: int | None = None
    rows_after: int | None = None


class Snapshot(BaseModel):
    id: str
    project_id: str
    file_id: str
    sheet: str | None = None
    parquet_path: str
    hash_before: str | None = None
    hash_after: str | None = None
    created_at: datetime
    proposal_id: str | None = None


class PipelineRuleYAML(BaseModel):
    """Persisted form of one applied cleansing rule (export/import)."""
    type: ProposalType
    target_columns: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
