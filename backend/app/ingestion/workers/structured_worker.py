"""Structured-data worker: xpt / sas7bdat / CDISC-shaped csv/xlsx → parquet."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import data_dir
from app.schemas.ingest import IngestResult
from app.ingestion.workers._common import profile_dataframe, raw_dir, write_parquet


def _load_sas(p: Path):
    import pandas as pd
    try:
        import pyreadstat  # type: ignore
    except ImportError:
        pyreadstat = None  # type: ignore
    if pyreadstat is not None:
        try:
            if p.suffix.lower() == ".xpt":
                df, meta = pyreadstat.read_xport(str(p))
            else:
                df, meta = pyreadstat.read_sas7bdat(str(p))
            return df, getattr(meta, "column_labels", None)
        except Exception:
            pass
    # pandas fallback: limited but works for many .xpt files
    if p.suffix.lower() == ".xpt":
        return pd.read_sas(str(p), format="xport"), None
    return pd.read_sas(str(p), format="sas7bdat"), None


def _load_table(p: Path):
    import pandas as pd
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p, dtype=str, encoding_errors="replace"), None
    return pd.read_excel(p, sheet_name=0, dtype=str), None


def _detect_adam_kind(cols: list[str]) -> str | None:
    up = {c.upper() for c in cols}
    if {"USUBJID", "TRT01P"} <= up and "AGE" in up:
        return "ADSL"
    if {"USUBJID", "AETERM"} <= up:
        return "ADAE"
    if {"USUBJID", "PARAMCD", "AVAL"} <= up:
        return "ADEFF"
    return None


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    rdir = raw_dir(project_id, file_id)
    ext = file_path.suffix.lower()
    notes: list[str] = []
    try:
        if ext in {".xpt", ".sas7bdat"}:
            df, _labels = _load_sas(file_path)
            notes.append(f"loaded SAS dataset rows={len(df)} cols={len(df.columns)}")
        else:
            df, _ = _load_table(file_path)
            notes.append(f"loaded tabular rows={len(df)} cols={len(df.columns)}")
    except Exception as e:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="structured_data",
            confidence=0.0, error=f"load failed: {e}",
        )

    cols = [str(c) for c in df.columns]
    adam_kind = _detect_adam_kind(cols)
    if adam_kind:
        notes.append(f"recognized as {adam_kind}")
    parquet_path = write_parquet(df, rdir / "data.parquet")
    profile = profile_dataframe(df, file_id=file_id)
    (rdir / "meta.json").write_text(json.dumps({
        "ingest_type": "structured_data",
        "adam_kind": adam_kind,
        "n_rows": int(df.shape[0]), "n_cols": int(df.shape[1]),
        "columns": cols,
        "source_filename": file_path.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="structured_data",
        confidence=0.95 if adam_kind else 0.85,
        artifacts={"parquet": parquet_path, "meta": str(rdir / "meta.json")},
        profiles=[profile], notes=notes,
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
