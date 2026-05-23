"""Subgroup analysis + forest plot StatBlock.

For each (subgroup variable × level) crossing we run a two-sample comparison
on ``outcome_col`` between the two ``group_col`` levels and capture the
Welch t-test mean difference + 95% CI + p-value. The collated table becomes
a forest plot rendered to both PNG (matplotlib) and ECharts JSON.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import (
    fmt_num, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


def _two_group_diff(arr_a: np.ndarray, arr_b: np.ndarray) -> dict[str, Any] | None:
    a = arr_a[~np.isnan(arr_a)]
    b = arr_b[~np.isnan(arr_b)]
    if len(a) < 2 or len(b) < 2:
        return None
    try:
        from scipy import stats
        res = stats.ttest_ind(a, b, equal_var=False)
        diff = float(a.mean() - b.mean())
        se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        num = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2
        den_a = (a.var(ddof=1) / len(a)) ** 2 / max(1, len(a) - 1) if a.var(ddof=1) > 0 else 0
        den_b = (b.var(ddof=1) / len(b)) ** 2 / max(1, len(b) - 1) if b.var(ddof=1) > 0 else 0
        dof = num / max(1e-9, den_a + den_b) if (den_a + den_b) > 0 else len(a) + len(b) - 2
        ci_mult = stats.t.ppf(0.975, dof) if dof > 0 else 1.96
        return {
            "n_a": int(len(a)), "n_b": int(len(b)),
            "mean_a": float(a.mean()), "mean_b": float(b.mean()),
            "diff": diff,
            "ci_low": diff - ci_mult * se,
            "ci_high": diff + ci_mult * se,
            "p_value": float(res.pvalue),
        }
    except Exception:
        return None


def _save_forest_png(rows: list[dict[str, Any]], out_path: Path,
                     title: str) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    if not rows:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    labels = [r["label"] for r in rows]
    diffs = [float(r["diff"]) for r in rows]
    lows = [float(r["ci_low"]) for r in rows]
    highs = [float(r["ci_high"]) for r in rows]
    err_low = [d - lo for d, lo in zip(diffs, lows)]
    err_hi = [hi - d for d, hi in zip(diffs, highs)]
    y = list(range(len(rows)))[::-1]   # top-to-bottom
    fig, ax = plt.subplots(figsize=(8, max(3, 0.45 * len(rows) + 1)))
    ax.errorbar(diffs, y, xerr=[err_low, err_hi], fmt="o",
                color="#1f4ed8", ecolor="#475569", capsize=4, markersize=6)
    ax.axvline(0, color="#94a3b8", linestyle="--", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Mean difference (A − B), 95% CI")
    ax.set_title(title, fontsize=11)
    for i, r in enumerate(rows):
        ax.text(max(highs) + (max(highs) - min(lows)) * 0.05,
                y[i], f"p={r['p_value']:.3g}", fontsize=8, va="center")
    fig.tight_layout()
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _echarts_forest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """ECharts 'custom' series for a forest plot: point + horizontal error bar."""
    data = []
    for i, r in enumerate(rows):
        data.append([i, r["diff"], r["ci_low"], r["ci_high"], r["p_value"]])
    return {
        "title": {"text": "Subgroup forest plot", "left": "center", "textStyle": {"fontSize": 13}},
        "grid": {"left": 200, "right": 80, "top": 50, "bottom": 40},
        "xAxis": {"type": "value", "name": "Mean diff (A − B)", "scale": True},
        "yAxis": {
            "type": "category",
            "data": [r["label"] for r in rows],
            "inverse": True,
        },
        "series": [{
            "type": "custom",
            "renderItem": "_inline_forest_render",
            "encode": {"x": [1, 2, 3], "y": 0},
            "data": data,
        }],
        "tooltip": {
            "trigger": "item",
            "formatter": "{b}: diff {c[1]:.3f} (95% CI {c[2]:.3f}, {c[3]:.3f}), p={c[4]:.3g}",
        },
    }


def subgroup_analysis(
    parquet_path: str,
    outcome_col: str,
    group_col: str,
    subgroup_cols: list[str],
    *,
    output_dir: str | None = None,
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in [outcome_col, group_col] + list(subgroup_cols) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="subgroup",
            title="亚组分析", params={
                "parquet_path": parquet_path, "outcome_col": outcome_col,
                "group_col": group_col, "subgroup_cols": subgroup_cols,
            },
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing={missing}"],
        )
    groups = df[group_col].dropna().unique().tolist()
    if len(groups) < 2:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="subgroup",
            title="亚组分析", params={
                "parquet_path": parquet_path, "outcome_col": outcome_col,
                "group_col": group_col, "subgroup_cols": subgroup_cols,
            },
            result_json={"error": f"group_col {group_col} needs ≥2 levels, got {groups}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(),
        )
    # Use first two levels (sorted for determinism)
    groups = sorted(map(str, groups))[:2]
    g_a, g_b = groups
    rows: list[dict[str, Any]] = []

    # Overall row
    a_vals = pd.to_numeric(df.loc[df[group_col].astype(str) == g_a, outcome_col],
                             errors="coerce").to_numpy()
    b_vals = pd.to_numeric(df.loc[df[group_col].astype(str) == g_b, outcome_col],
                             errors="coerce").to_numpy()
    overall = _two_group_diff(a_vals, b_vals)
    if overall:
        rows.append({"label": "Overall", "subgroup": "ALL", "level": "All",
                     **overall})

    # Per subgroup variable
    for sub in subgroup_cols:
        levels = sorted({str(v) for v in df[sub].dropna().unique()})
        for lvl in levels:
            sub_df = df[df[sub].astype(str) == lvl]
            a = pd.to_numeric(sub_df.loc[sub_df[group_col].astype(str) == g_a, outcome_col],
                                errors="coerce").to_numpy()
            b = pd.to_numeric(sub_df.loc[sub_df[group_col].astype(str) == g_b, outcome_col],
                                errors="coerce").to_numpy()
            r = _two_group_diff(a, b)
            if r is None:
                continue
            rows.append({"label": f"{sub}={lvl}", "subgroup": sub, "level": lvl, **r})

    if not rows:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="subgroup",
            title="亚组分析", params={
                "parquet_path": parquet_path, "outcome_col": outcome_col,
                "group_col": group_col, "subgroup_cols": subgroup_cols,
            },
            result_json={"error": "no subgroup had ≥2 obs in each arm"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(),
        )

    # Markdown table
    tbl_rows: list[list[Any]] = []
    for r in rows:
        n_total = r["n_a"] + r["n_b"]
        tbl_rows.append([
            r["label"], n_total, f"{r['n_a']}/{r['n_b']}",
            fmt_num(r["diff"], 3),
            f"[{fmt_num(r['ci_low'], 3)}, {fmt_num(r['ci_high'], 3)}]",
            fmt_num(r["p_value"], 4),
        ])
    headers = ["Subgroup", "N", "n(A)/n(B)", "Mean Δ", "95% CI", "p"]
    table_md = md_table(tbl_rows, headers)

    # Forest plot PNG + ECharts JSON
    out_dir = Path(output_dir) if output_dir else Path(".") / "_subgroup_out"
    png_path = _save_forest_png(rows, out_dir / f"forest_{new_stat_id()}.png",
                                 title=f"{outcome_col} by {group_col}")
    chart_json = _echarts_forest(rows)

    notes = [f"n_subgroups={len(rows)}",
             f"arms={g_a} vs {g_b}",
             f"png={'yes' if png_path else 'no'}"]
    result_json = jsonable_dict({
        "outcome_col": outcome_col, "group_col": group_col,
        "subgroup_cols": list(subgroup_cols),
        "arms": [g_a, g_b],
        "rows": rows,
        "png_path": str(png_path) if png_path else None,
        "chart_json": chart_json,
    })
    md = (
        f"**亚组分析 — {outcome_col} by {group_col} ({g_a} vs {g_b})**\n\n"
        + table_md
        + (f"\n\n*Forest plot:* `{png_path.name}`" if png_path else "")
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="subgroup",
        title=f"亚组分析（{outcome_col} by {group_col}）",
        params={
            "parquet_path": parquet_path, "outcome_col": outcome_col,
            "group_col": group_col, "subgroup_cols": list(subgroup_cols),
        },
        result_json=result_json, markdown_table=md,
        source_files=[parquet_path], created_at=now_utc(), notes=notes,
    )
