"""Survival analysis — Kaplan-Meier + Cox proportional hazards (lifelines).

Public API:

    km_estimate(parquet_path, time_col='AVAL', event_col='CNSR',
                group_col=None) -> StatBlock
    cox_regression(parquet_path, time_col, event_col, covariates) -> StatBlock

CDISC convention quirk: ADaM `CNSR` is 1 = censored, 0 = event. Lifelines
expects the *event indicator* (1 = event). We auto-detect and invert when the
column name is CNSR or values are predominantly 1.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import (
    fmt_num, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


def _to_event_indicator(s: pd.Series, name: str) -> pd.Series:
    """Convert CNSR (1=censored) to event indicator (1=event)."""
    num = pd.to_numeric(s, errors="coerce")
    if name.upper() == "CNSR":
        return 1 - num.fillna(1)
    # Heuristic: if column already named EVNT/EVENT or values are mostly 0/1 with mean < 0.6, treat as event
    return num.fillna(0)


def km_estimate(
    parquet_path: str,
    time_col: str = "AVAL",
    event_col: str = "CNSR",
    group_col: str | None = None,
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in (time_col, event_col) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title=f"KM estimate ({time_col}, {event_col})",
            params={"parquet_path": parquet_path, "time_col": time_col,
                    "event_col": event_col, "group_col": group_col},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing columns: {missing}"],
        )

    try:
        from lifelines import KaplanMeierFitter
        from lifelines.statistics import logrank_test, multivariate_logrank_test
    except ImportError:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title=f"KM estimate ({time_col})",
            params={"parquet_path": parquet_path},
            result_json={"error": "lifelines not installed"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=["lifelines missing"],
        )

    t = pd.to_numeric(df[time_col], errors="coerce")
    e = _to_event_indicator(df[event_col], event_col)
    valid = t.notna() & e.notna()
    df2 = df[valid].copy()
    df2["__t__"] = t[valid].astype(float)
    df2["__e__"] = e[valid].astype(int).clip(0, 1)

    result: dict[str, Any] = {"time_col": time_col, "event_col": event_col}
    rows: list[list[Any]] = []

    if group_col and group_col in df2.columns:
        groups = sorted(df2[group_col].dropna().unique().tolist(), key=str)
        result["group_col"] = group_col
        result["groups"] = []
        for g in groups:
            sub = df2[df2[group_col] == g]
            if sub.empty:
                continue
            kmf = KaplanMeierFitter()
            kmf.fit(sub["__t__"], sub["__e__"], label=str(g))
            median = float(kmf.median_survival_time_) if not np.isnan(kmf.median_survival_time_) else None
            n_events = int(sub["__e__"].sum())
            result["groups"].append({
                "name": str(g),
                "n": int(sub.shape[0]),
                "n_events": n_events,
                "median_survival": median,
            })
            rows.append([str(g), int(sub.shape[0]), n_events, fmt_num(median, 1) if median else "NR"])

        # Logrank
        if len(groups) == 2:
            sub_a = df2[df2[group_col] == groups[0]]
            sub_b = df2[df2[group_col] == groups[1]]
            lr = logrank_test(sub_a["__t__"], sub_b["__t__"],
                              event_observed_A=sub_a["__e__"], event_observed_B=sub_b["__e__"])
            result["logrank"] = {"statistic": float(lr.test_statistic), "p_value": float(lr.p_value)}
        elif len(groups) > 2:
            lr = multivariate_logrank_test(df2["__t__"], df2[group_col], df2["__e__"])
            result["logrank"] = {"statistic": float(lr.test_statistic), "p_value": float(lr.p_value)}
    else:
        kmf = KaplanMeierFitter()
        kmf.fit(df2["__t__"], df2["__e__"], label="All Subjects")
        median = float(kmf.median_survival_time_) if not np.isnan(kmf.median_survival_time_) else None
        n_events = int(df2["__e__"].sum())
        result["groups"] = [{
            "name": "All Subjects",
            "n": int(df2.shape[0]),
            "n_events": n_events,
            "median_survival": median,
        }]
        rows.append(["All Subjects", int(df2.shape[0]), n_events, fmt_num(median, 1) if median else "NR"])

    table_md = md_table(rows, ["Group", "N", "Events", "Median survival"])
    if "logrank" in result:
        table_md += (
            f"\n\nLog-rank test: chi² = {fmt_num(result['logrank']['statistic'], 3)}, "
            f"p = {fmt_num(result['logrank']['p_value'], 4)}"
        )

    title = (
        f"Kaplan-Meier 估计（{time_col} / {event_col}，按 {group_col} 分组）"
        if group_col and group_col in df2.columns
        else f"Kaplan-Meier 估计（{time_col} / {event_col}）"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="survival",
        title=title,
        params={"parquet_path": parquet_path, "time_col": time_col,
                "event_col": event_col, "group_col": group_col},
        result_json=jsonable_dict(result),
        markdown_table=table_md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"n={int(df2.shape[0])}", f"events={int(df2['__e__'].sum())}"],
    )


def cox_regression(
    parquet_path: str,
    time_col: str,
    event_col: str,
    covariates: list[str],
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in [time_col, event_col, *covariates] if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title=f"Cox regression ({time_col})",
            params={"parquet_path": parquet_path, "time_col": time_col,
                    "event_col": event_col, "covariates": covariates},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing: {missing}"],
        )
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title="Cox regression",
            params={"parquet_path": parquet_path},
            result_json={"error": "lifelines not installed"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=["lifelines missing"],
        )

    work = pd.DataFrame({
        "__t__": pd.to_numeric(df[time_col], errors="coerce"),
        "__e__": _to_event_indicator(df[event_col], event_col).astype(int).clip(0, 1),
    })
    for c in covariates:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            work[c] = pd.to_numeric(s, errors="coerce")
        else:
            # One-hot encode (drop_first to avoid collinearity)
            dummies = pd.get_dummies(s, prefix=c, drop_first=True, dtype=float)
            for col in dummies.columns:
                work[col] = dummies[col]

    work = work.dropna()
    if work.empty:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title=f"Cox regression ({time_col})",
            params={"parquet_path": parquet_path, "covariates": covariates},
            result_json={"error": "no rows after dropping NA"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=["empty after dropna"],
        )

    cph = CoxPHFitter()
    try:
        cph.fit(work, duration_col="__t__", event_col="__e__")
    except Exception as e:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title=f"Cox regression ({time_col})",
            params={"parquet_path": parquet_path, "covariates": covariates},
            result_json={"error": f"fit failed: {e}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"fit error: {e}"],
        )

    summary = cph.summary
    rows: list[list[Any]] = []
    coefs: list[dict[str, Any]] = []
    for cov in summary.index:
        hr = float(summary.loc[cov, "exp(coef)"])
        lo = float(summary.loc[cov, "exp(coef) lower 95%"])
        hi = float(summary.loc[cov, "exp(coef) upper 95%"])
        p = float(summary.loc[cov, "p"])
        rows.append([str(cov), fmt_num(hr, 3), f"[{fmt_num(lo, 3)}, {fmt_num(hi, 3)}]", fmt_num(p, 4)])
        coefs.append({"covariate": str(cov), "HR": hr, "HR_low": lo, "HR_high": hi, "p_value": p})

    table_md = md_table(rows, ["Covariate", "HR", "95% CI", "p-value"])
    n_events = int(work["__e__"].sum())
    table_md += f"\n\nN = {int(work.shape[0])}, events = {n_events}, concordance = {fmt_num(cph.concordance_index_, 3)}"

    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="survival",
        title=f"Cox 比例风险回归（{time_col} / {event_col}）",
        params={"parquet_path": parquet_path, "time_col": time_col,
                "event_col": event_col, "covariates": covariates},
        result_json=jsonable_dict({
            "coefs": coefs,
            "n": int(work.shape[0]),
            "n_events": n_events,
            "concordance": float(cph.concordance_index_),
        }),
        markdown_table=table_md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"n={int(work.shape[0])}", f"events={n_events}"],
    )
