"""Baseline balance — standardized mean difference (SMD).

Reports per-variable SMD between two arms of ``group_col``; |SMD| > 0.1 is
flagged as imbalanced (the standard threshold in clinical trial literature).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import (
    fmt_num, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


def _smd_continuous(a: np.ndarray, b: np.ndarray) -> float | None:
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = math.sqrt((va + vb) / 2) if (va + vb) > 0 else 0.0
    if pooled == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def _smd_categorical(a: pd.Series, b: pd.Series) -> float | None:
    a = a.dropna(); b = b.dropna()
    if a.empty or b.empty:
        return None
    levels = sorted(set(a.astype(str).unique()) | set(b.astype(str).unique()))
    if not levels:
        return None
    pa = np.array([float((a.astype(str) == lvl).mean()) for lvl in levels])
    pb = np.array([float((b.astype(str) == lvl).mean()) for lvl in levels])
    # Multi-level SMD (Yang & Dalton): sqrt((pa-pb)' S^-1 (pa-pb))
    diff = pa - pb
    # Simplified scalar: use sum of (p_a-p_b)^2 / pooled variance
    pooled_var = (pa * (1 - pa) + pb * (1 - pb)) / 2
    pooled_var = np.where(pooled_var == 0, 1e-9, pooled_var)
    smd_levels = np.abs(diff) / np.sqrt(pooled_var)
    return float(smd_levels.max())


def smd_test(
    parquet_path: str,
    group_col: str,
    vars: list[str],
    threshold: float = 0.1,
) -> StatBlock:
    df = load_parquet(parquet_path)
    if group_col not in df.columns:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="baseline_balance",
            title="基线平衡（SMD）",
            params={"parquet_path": parquet_path, "group_col": group_col, "vars": list(vars)},
            result_json={"error": f"missing group_col {group_col}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(),
        )
    groups = sorted(map(str, df[group_col].dropna().unique()))[:2]
    if len(groups) < 2:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="baseline_balance",
            title="基线平衡（SMD）",
            params={"parquet_path": parquet_path, "group_col": group_col, "vars": list(vars)},
            result_json={"error": f"need ≥2 levels in {group_col}, got {groups}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(),
        )
    g_a, g_b = groups
    df_a = df[df[group_col].astype(str) == g_a]
    df_b = df[df[group_col].astype(str) == g_b]
    rows: list[list[Any]] = []
    detail: list[dict[str, Any]] = []
    for v in vars:
        if v not in df.columns:
            continue
        numeric = pd.to_numeric(df[v], errors="coerce").notna().sum() / max(1, df[v].notna().sum()) > 0.6
        if numeric:
            arr_a = pd.to_numeric(df_a[v], errors="coerce").to_numpy()
            arr_b = pd.to_numeric(df_b[v], errors="coerce").to_numpy()
            smd = _smd_continuous(arr_a, arr_b)
            mean_a = pd.to_numeric(df_a[v], errors="coerce").mean()
            mean_b = pd.to_numeric(df_b[v], errors="coerce").mean()
            disp_a = fmt_num(mean_a, 2); disp_b = fmt_num(mean_b, 2)
            kind = "continuous"
        else:
            smd = _smd_categorical(df_a[v], df_b[v])
            disp_a = f"{int(df_a[v].notna().sum())} obs"
            disp_b = f"{int(df_b[v].notna().sum())} obs"
            kind = "categorical"
        if smd is None:
            continue
        balanced = abs(smd) < threshold
        rows.append([v, disp_a, disp_b, fmt_num(smd, 3),
                     "Yes" if balanced else "No", kind])
        detail.append({"variable": v, "smd": float(smd),
                       "kind": kind, "balanced": bool(balanced)})
    table_md = md_table(rows, ["Variable", f"{g_a}", f"{g_b}", "|SMD|", "Balanced", "Type"])
    n_imbalanced = sum(1 for r in detail if not r["balanced"])
    md = (
        f"**基线平衡（SMD） — {group_col} ({g_a} vs {g_b})**\n\n"
        + table_md
        + f"\n\nThreshold: |SMD| < {threshold} ⇒ balanced.  "
        + f"Imbalanced variables: {n_imbalanced}/{len(detail)}"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="baseline_balance",
        title=f"基线平衡（SMD by {group_col}）",
        params={"parquet_path": parquet_path, "group_col": group_col,
                "vars": list(vars), "threshold": threshold},
        result_json=jsonable_dict({
            "arms": [g_a, g_b], "threshold": threshold,
            "variables": detail, "n_imbalanced": n_imbalanced,
        }),
        markdown_table=md, source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"n_vars={len(detail)}", f"n_imbalanced={n_imbalanced}"],
    )
