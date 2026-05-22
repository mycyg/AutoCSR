"""Descriptive analysis — baseline / demographics tables.

Public API:

    baseline_table(parquet_path, group_col='TRT01P',
                   cont_cols=['AGE','HEIGHT','WEIGHT','BMI'],
                   cat_cols=['SEX','RACE'],
                   filter_query=None) -> StatBlock

Robustness rules:
    - missing column -> silently skipped
    - all-NaN column -> blank cell, no crash
    - 0-row group -> "0" / blank
    - group_col absent -> a single "All Subjects" column
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.analysis._common import (
    filter_df, fmt_num, has_cols, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


DEFAULT_CONT = ["AGE", "HEIGHT", "WEIGHT", "BMI"]
DEFAULT_CAT = ["SEX", "RACE"]


def _continuous_cell(s: pd.Series) -> str:
    """Render mean ± SD (median [IQR]) — blank when all NaN."""
    num = pd.to_numeric(s, errors="coerce").dropna()
    if num.empty:
        return ""
    mean = num.mean()
    sd = num.std(ddof=1) if num.size > 1 else 0.0
    med = num.median()
    q1, q3 = num.quantile(0.25), num.quantile(0.75)
    return f"{fmt_num(mean, 1)} ± {fmt_num(sd, 1)} ({fmt_num(med, 1)} [{fmt_num(q1, 1)}, {fmt_num(q3, 1)}])"


def _categorical_cells(s: pd.Series) -> list[tuple[str, int, int]]:
    """Return [(value, count, total_non_null), ...] sorted by frequency."""
    s2 = s.dropna()
    total = int(s2.size)
    counts = s2.astype(str).value_counts()
    return [(str(k), int(v), total) for k, v in counts.items()]


def baseline_table(
    parquet_path: str,
    group_col: str = "TRT01P",
    cont_cols: list[str] | None = None,
    cat_cols: list[str] | None = None,
    filter_query: str | None = None,
) -> StatBlock:
    df = load_parquet(parquet_path)
    df = filter_df(df, filter_query)
    cont_cols = cont_cols if cont_cols is not None else DEFAULT_CONT
    cat_cols = cat_cols if cat_cols is not None else DEFAULT_CAT
    cont_cols = has_cols(df, cont_cols)
    cat_cols = has_cols(df, cat_cols)

    # Resolve grouping
    if group_col in df.columns:
        grouped = list(df.groupby(group_col, dropna=False, observed=False))
        group_names: list[str] = [str(g) if not pd.isna(g) else "Missing" for g, _ in grouped]
        groups: list[pd.DataFrame] = [g_df for _, g_df in grouped]
    else:
        group_names = ["All Subjects"]
        groups = [df]

    n_by_group = [int(g.shape[0]) for g in groups]

    # Build rows
    rows: list[list[Any]] = []

    # First row: N
    rows.append(["**N (subjects)**"] + [str(n) for n in n_by_group] + [str(int(df.shape[0]))])

    for c in cont_cols:
        cells = [_continuous_cell(g[c]) if c in g.columns else "" for g in groups]
        total_cell = _continuous_cell(df[c]) if c in df.columns else ""
        rows.append([f"{c}, mean ± SD (median [IQR])"] + cells + [total_cell])

    for c in cat_cols:
        # Header row for the categorical variable
        rows.append([f"**{c}**, n (%)"] + ["" for _ in groups] + [""])
        # Determine all levels across groups
        levels: list[str] = []
        seen: set[str] = set()
        for g in groups + [df]:
            if c not in g.columns:
                continue
            for v in g[c].dropna().astype(str).unique().tolist():
                if v not in seen:
                    seen.add(v)
                    levels.append(v)
        for lvl in levels:
            cells: list[Any] = []
            for g, n in zip(groups, n_by_group):
                if c not in g.columns:
                    cells.append("")
                    continue
                k = int((g[c].astype(str) == lvl).sum())
                pct = (k / n * 100) if n > 0 else 0.0
                cells.append(f"{k} ({pct:.1f}%)")
            k_total = int((df[c].astype(str) == lvl).sum()) if c in df.columns else 0
            n_total = int(df.shape[0])
            pct_total = (k_total / n_total * 100) if n_total > 0 else 0.0
            rows.append([f"&nbsp;&nbsp;{lvl}"] + cells + [f"{k_total} ({pct_total:.1f}%)"])

    headers = ["Variable"] + [f"{g} (N={n})" for g, n in zip(group_names, n_by_group)] + [f"Total (N={int(df.shape[0])})"]
    table_md = md_table(rows, headers)

    title = f"基线人口学（按 {group_col} 分组）" if group_col in df.columns else "基线人口学（全体）"

    result_json: dict[str, Any] = jsonable_dict({
        "group_col": group_col if group_col in df.columns else None,
        "group_names": group_names,
        "n_by_group": n_by_group,
        "n_total": int(df.shape[0]),
        "continuous_vars": cont_cols,
        "categorical_vars": cat_cols,
        "filter": filter_query,
    })

    return StatBlock(
        id=new_stat_id(),
        project_id="",                       # filled in by store.save()
        analysis_type="descriptive",
        title=title,
        params={
            "parquet_path": parquet_path,
            "group_col": group_col,
            "cont_cols": cont_cols,
            "cat_cols": cat_cols,
            "filter_query": filter_query,
        },
        result_json=result_json,
        markdown_table=table_md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"n_total={df.shape[0]}", f"groups={len(group_names)}"],
    )
