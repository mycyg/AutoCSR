"""Deterministic cleansing-proposal coverage (M17)."""
from __future__ import annotations

from app.cleansing.proposer import _deterministic
from app.schemas.ingest import ColumnProfile, DataProfile, IngestResult


def _profile(cols: list[ColumnProfile], rows: int = 100) -> DataProfile:
    return DataProfile(
        file_id="f1", sheet=None, n_rows=rows, n_cols=len(cols), columns=cols,
    )


def _ingest() -> IngestResult:
    return IngestResult(
        file_id="f1", project_id="proj1", ingest_type="structured_data",
        confidence=0.95,
    )


def test_hash_pii_is_mandatory_when_column_flagged_pii():
    cols = [ColumnProfile(
        name="email", dtype="object", null_rate=0.0, n_unique=10,
        sample_values=["a@b.com"], suspected_pii=True, suspected_role="email",
    )]
    out = _deterministic(_profile(cols), _ingest())
    pii_props = [p for p in out if p.type == "hash_pii"]
    assert len(pii_props) == 1
    assert pii_props[0].mandatory is True
    assert pii_props[0].target_columns == ["email"]


def test_cast_dtype_proposed_for_numeric_object_column():
    cols = [ColumnProfile(
        name="age_text", dtype="object", null_rate=0.05, n_unique=80,
        sample_values=["52", "47"], numeric_min=18, numeric_max=92,
        numeric_mean=55.0, suspected_role="age",
    )]
    out = _deterministic(_profile(cols), _ingest())
    casts = [p for p in out if p.type == "cast_dtype"]
    assert casts and casts[0].parameters.get("to") == "float"


def test_impute_missing_proposed_for_mid_null_rate():
    cols = [ColumnProfile(
        name="weight", dtype="float64", null_rate=0.2, n_unique=70,
        numeric_min=40, numeric_max=120, numeric_mean=75.0,
    )]
    out = _deterministic(_profile(cols), _ingest())
    imps = [p for p in out if p.type == "impute_missing"]
    assert imps and imps[0].parameters.get("strategy") == "median"


def test_outlier_flag_proposed_when_outliers_detected():
    cols = [ColumnProfile(
        name="bp", dtype="float64", null_rate=0.0, n_unique=80,
        numeric_min=60, numeric_max=240, numeric_mean=120.0,
        numeric_outlier_count=5,
    )]
    out = _deterministic(_profile(cols), _ingest())
    outliers = [p for p in out if p.type == "outlier_flag"]
    assert outliers
    assert outliers[0].parameters.get("method") == "iqr"


def test_clean_column_yields_no_proposals():
    cols = [ColumnProfile(
        name="visit", dtype="object", null_rate=0.0, n_unique=4,
        sample_values=["V1", "V2", "V3", "V4"], suspected_pii=False,
    )]
    out = _deterministic(_profile(cols), _ingest())
    # No pii, no cast (string-y), no impute, no outliers
    assert out == []
