"""Re-profile any pandas DataFrame on demand.

Reuses ingestion._common.profile_dataframe — kept thin so callers can recompute
post-transform profiles without a special path.
"""
from __future__ import annotations

from pathlib import Path

from app.ingestion.workers._common import profile_dataframe
from app.schemas.ingest import DataProfile


def profile_path(parquet_or_csv: Path, *, file_id: str, sheet: str | None = None) -> DataProfile:
    import pandas as pd
    if parquet_or_csv.suffix.lower() == ".parquet":
        df = pd.read_parquet(parquet_or_csv)
    else:
        df = pd.read_csv(parquet_or_csv, dtype=str, encoding_errors="replace")
    return profile_dataframe(df, file_id=file_id, sheet=sheet)
