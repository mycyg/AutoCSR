"""Ingestion schemas — Router type tags + IngestResult + DataProfile."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


IngestType = Literal[
    "structured_data",   # SAS xpt, sas7bdat, SDTM/ADaM-shaped csv/xlsx
    "messy_tabular",     # csv/xlsx without ADaM dictionary, needs cleansing
    "pdf_form",          # text-PDF with fields / structured forms
    "scan_crf",          # image PDF / scanned CRF
    "handwriting",       # contains handwritten regions (M2.5)
    "literature_doc",    # protocol, SAP, IB, paper — narrative
]


class FileEntry(BaseModel):
    file_id: str
    project_id: str
    filename: str
    mime: str | None = None
    size_bytes: int = 0
    stored_path: str         # absolute path on disk
    uploaded_at: datetime
    ingest_type: IngestType | None = None
    ingest_confidence: float | None = None
    needs_user_confirm: bool = False
    status: Literal["uploaded", "routing", "running", "done", "error"] = "uploaded"
    error: str | None = None


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    null_rate: float
    n_unique: int
    sample_values: list[str] = Field(default_factory=list)
    top_freq: list[tuple[str, int]] = Field(default_factory=list)
    numeric_min: float | None = None
    numeric_max: float | None = None
    numeric_mean: float | None = None
    numeric_outlier_count: int | None = None
    suspected_role: str | None = None  # USUBJID, AGE, TRT01P, AETERM, etc.
    suspected_pii: bool = False


class DataProfile(BaseModel):
    file_id: str
    sheet: str | None = None
    n_rows: int
    n_cols: int
    columns: list[ColumnProfile]
    encoding_issues: list[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    file_id: str
    project_id: str
    ingest_type: IngestType
    confidence: float
    artifacts: dict[str, str] = Field(default_factory=dict)  # parquet_path, meta_path, etc.
    profiles: list[DataProfile] = Field(default_factory=list)
    corpus_block_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False
    notes: list[str] = Field(default_factory=list)
    error: str | None = None
