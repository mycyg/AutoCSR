"""Re-profile any pandas DataFrame on demand.

Reuses ingestion._common.profile_dataframe — kept thin so callers can recompute
post-transform profiles without a special path.

M11: ``detect_anomalies`` walks a DataProfile and emits thresholded
Anomaly objects which the alerts aggregator consumes.
"""
from __future__ import annotations

from pathlib import Path

from app.ingestion.workers._common import profile_dataframe
from app.schemas.ingest import Anomaly, ColumnProfile, DataProfile


# Thresholds
_NULL_WARN = 0.5         # >50% null → warn
_NULL_ERROR = 0.8        # >80% null → error
_OUTLIER_INFO_PCT = 0.1  # >10% IQR outliers → info


def detect_anomalies(profile: DataProfile) -> list[Anomaly]:
    """Compute a fresh anomaly list from a DataProfile.

    Idempotent — callers can call this every time the profile is
    re-evaluated. The new list overwrites ``profile.anomalies`` (the
    caller decides whether to mutate or create a copy).
    """
    anomalies: list[Anomaly] = []
    n_rows = profile.n_rows or 0

    for col in profile.columns:
        # Null rate thresholds
        if col.null_rate > _NULL_ERROR:
            anomalies.append(Anomaly(
                severity="error", column=col.name,
                value=f"{col.null_rate:.0%}",
                message=f"列 {col.name} 缺失率 {col.null_rate:.0%}，超过 80% 红线，"
                        f"建议核查源数据或剔除该列。",
            ))
        elif col.null_rate > _NULL_WARN:
            anomalies.append(Anomaly(
                severity="warn", column=col.name,
                value=f"{col.null_rate:.0%}",
                message=f"列 {col.name} 缺失率 {col.null_rate:.0%}，超过 50%，"
                        f"请评估是否需要插补。",
            ))
        # Outlier rate
        if (col.numeric_outlier_count is not None and n_rows > 0
                and col.numeric_outlier_count / max(n_rows, 1) > _OUTLIER_INFO_PCT):
            anomalies.append(Anomaly(
                severity="info", column=col.name,
                value=str(col.numeric_outlier_count),
                message=f"列 {col.name} 检测到 {col.numeric_outlier_count} 个 IQR 离群点 "
                        f"({col.numeric_outlier_count / max(n_rows, 1):.0%})。",
            ))
        # PII columns without explicit hash
        if col.suspected_pii:
            anomalies.append(Anomaly(
                severity="warn", column=col.name,
                message=f"列 {col.name} 疑似含 PII，请确认 hash_pii 已开启。",
            ))

    # Encoding issues bubble up as warnings
    for msg in profile.encoding_issues:
        anomalies.append(Anomaly(severity="warn", message=msg))
    return anomalies


def profile_path(parquet_or_csv: Path, *, file_id: str, sheet: str | None = None) -> DataProfile:
    import pandas as pd
    if parquet_or_csv.suffix.lower() == ".parquet":
        df = pd.read_parquet(parquet_or_csv)
    else:
        df = pd.read_csv(parquet_or_csv, dtype=str, encoding_errors="replace")
    profile = profile_dataframe(df, file_id=file_id, sheet=sheet)
    # Populate anomalies inline; downstream caching uses the same object.
    return profile.model_copy(update={"anomalies": detect_anomalies(profile)})
