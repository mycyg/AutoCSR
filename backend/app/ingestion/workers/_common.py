"""Shared helpers for ingestion workers."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.schemas.ingest import ColumnProfile, DataProfile

# CDISC-ish role hints — used both by router and profiler.
ROLE_HINTS: dict[str, str] = {
    "USUBJID": "subject_id", "SUBJID": "subject_id", "PATIENT_ID": "subject_id",
    "PATID": "subject_id", "ID": "subject_id",
    "AGE": "age", "SEX": "sex", "GENDER": "sex", "RACE": "race",
    "TRT01P": "treatment", "TRT01A": "treatment", "ARM": "treatment", "ARMCD": "treatment",
    "AETERM": "ae_term", "AESOC": "ae_soc", "AEDECOD": "ae_decode",
    "AESEV": "ae_severity", "AESER": "ae_serious",
    "VISIT": "visit", "VISITNUM": "visit_num",
}

PII_LIKELY = {
    "subject_id", "patient_name", "phone", "email", "address",
    "national_id", "id_card", "passport", "mrn",
}

PII_NAME_TOKENS = ("姓名", "name", "phone", "电话", "身份证", "id_card",
                   "address", "地址", "email", "邮箱", "mrn")


def raw_dir(project_id: str, file_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "raw" / file_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def suspect_role(col_name: str) -> str | None:
    up = col_name.strip().upper()
    if up in ROLE_HINTS:
        return ROLE_HINTS[up]
    low = col_name.lower()
    for tok in PII_NAME_TOKENS:
        if tok in low:
            return "patient_name" if tok in ("姓名", "name") else "pii_other"
    return None


def suspect_pii(col_name: str, role: str | None) -> bool:
    if role in PII_LIKELY:
        return True
    low = col_name.lower()
    return any(tok in low for tok in PII_NAME_TOKENS)


def profile_dataframe(df, *, file_id: str, sheet: str | None = None) -> DataProfile:
    """Build a DataProfile from a pandas DataFrame. Robust to mixed dtypes."""
    import pandas as pd

    n_rows, n_cols = df.shape
    columns: list[ColumnProfile] = []
    enc_issues: list[str] = []

    for col in df.columns:
        s = df[col]
        try:
            null_rate = float(s.isna().mean())
        except Exception:
            null_rate = 0.0
        try:
            n_unique = int(s.nunique(dropna=True))
        except Exception:
            n_unique = 0
        sample_values = [
            "" if pd.isna(v) else str(v)[:60]
            for v in s.dropna().head(5).tolist()
        ]
        try:
            vc = s.dropna().astype(str).value_counts().head(5)
            top_freq = [(str(k), int(v)) for k, v in vc.items()]
        except Exception:
            top_freq = []
        dtype = str(s.dtype)
        numeric_min = numeric_max = numeric_mean = None
        numeric_outlier_count = None
        try:
            num = pd.to_numeric(s, errors="coerce")
            if num.notna().any():
                numeric_min = float(num.min())
                numeric_max = float(num.max())
                m = float(num.mean())
                numeric_mean = m if not math.isnan(m) else None
                q1, q3 = float(num.quantile(0.25)), float(num.quantile(0.75))
                iqr = q3 - q1
                if iqr > 0:
                    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    numeric_outlier_count = int(((num < lo) | (num > hi)).sum())
        except Exception:
            pass

        # Encoding heuristic: stringified mojibake markers
        try:
            joined = "|".join(sample_values)
            if any(bad in joined for bad in ("�", "Â", "ï¿½")):
                enc_issues.append(f"column {col}: possible encoding mojibake")
        except Exception:
            pass

        role = suspect_role(str(col))
        columns.append(ColumnProfile(
            name=str(col), dtype=dtype, null_rate=null_rate, n_unique=n_unique,
            sample_values=sample_values, top_freq=top_freq,
            numeric_min=numeric_min, numeric_max=numeric_max,
            numeric_mean=numeric_mean, numeric_outlier_count=numeric_outlier_count,
            suspected_role=role, suspected_pii=suspect_pii(str(col), role),
        ))

    return DataProfile(
        file_id=file_id, sheet=sheet,
        n_rows=int(n_rows), n_cols=int(n_cols),
        columns=columns, encoding_issues=enc_issues,
    )


def write_parquet(df, out_path: Path) -> str:
    """Best-effort parquet write — falls back to CSV when pyarrow / engine fails."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(out_path, index=False)
        return str(out_path)
    except Exception:
        # parquet engines or odd dtypes → fall back to CSV with same stem
        csv_path = out_path.with_suffix(".csv")
        df.to_csv(csv_path, index=False, encoding="utf-8")
        return str(csv_path)
