"""Inferential analysis — two-group comparison tests.

Public API:

    compare_groups(parquet_path, group_col, value_col,
                   test='auto'|'t'|'wilcoxon'|'chi2'|'fisher',
                   filter_query=None) -> StatBlock

Auto rules:
    - value_col numeric, 2 groups, both n>=3, Shapiro p>=0.05 in both -> t-test
    - value_col numeric, otherwise                                    -> Wilcoxon
    - value_col categorical, 2x2 table with any expected cell <5      -> Fisher
    - value_col categorical, otherwise                                -> chi2

Output result_json carries: statistic, p_value, dof (if applicable),
ci_low/ci_high (95% CI for difference when t), method name.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from app.analysis._common import (
    filter_df, fmt_num, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


def _is_numeric(s: pd.Series) -> bool:
    num = pd.to_numeric(s, errors="coerce")
    # >= 70% of non-null values parse cleanly as numeric
    nonnull = s.dropna()
    if nonnull.empty:
        return False
    return num.notna().sum() / max(1, nonnull.size) >= 0.7


def _pick_test(df: pd.DataFrame, group_col: str, value_col: str) -> str:
    if _is_numeric(df[value_col]):
        groups = df[group_col].dropna().unique().tolist()
        if len(groups) != 2:
            return "kruskal"
        arrs: list[np.ndarray] = []
        for g in groups:
            arr = pd.to_numeric(df.loc[df[group_col] == g, value_col], errors="coerce").dropna().values
            arrs.append(arr)
        if min(len(a) for a in arrs) < 3:
            return "wilcoxon"
        # Shapiro for normality (small n only — beyond ~5000 it's overpowered)
        try:
            normal = all(stats.shapiro(a[:5000]).pvalue >= 0.05 for a in arrs if len(a) >= 3)
        except Exception:
            normal = False
        return "t" if normal else "wilcoxon"
    # Categorical
    return "chi2_or_fisher"


def _ttest_block(df: pd.DataFrame, group_col: str, value_col: str) -> tuple[dict[str, Any], list[list[Any]], list[str]]:
    groups = df[group_col].dropna().unique().tolist()
    a = pd.to_numeric(df.loc[df[group_col] == groups[0], value_col], errors="coerce").dropna().values
    b = pd.to_numeric(df.loc[df[group_col] == groups[1], value_col], errors="coerce").dropna().values
    if len(a) < 2 or len(b) < 2:
        return _empty_result("t-test", "n<2"), [], []
    res = stats.ttest_ind(a, b, equal_var=False)
    diff = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    # Approximate Welch dof
    if a.var(ddof=1) == 0 and b.var(ddof=1) == 0:
        dof = len(a) + len(b) - 2
    else:
        num = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2
        den_a = (a.var(ddof=1) / len(a)) ** 2 / max(1, len(a) - 1) if a.var(ddof=1) > 0 else 0
        den_b = (b.var(ddof=1) / len(b)) ** 2 / max(1, len(b) - 1) if b.var(ddof=1) > 0 else 0
        dof = num / max(1e-9, den_a + den_b)
    ci_mult = stats.t.ppf(0.975, dof) if dof > 0 else 1.96
    ci_lo = diff - ci_mult * se
    ci_hi = diff + ci_mult * se
    result = {
        "method": "Welch t-test",
        "groups": [str(g) for g in groups],
        "n": [int(len(a)), int(len(b))],
        "mean": [float(a.mean()), float(b.mean())],
        "sd": [float(a.std(ddof=1)) if len(a) > 1 else 0.0,
               float(b.std(ddof=1)) if len(b) > 1 else 0.0],
        "diff": float(diff),
        "ci_low": float(ci_lo),
        "ci_high": float(ci_hi),
        "statistic": float(res.statistic),
        "dof": float(dof),
        "p_value": float(res.pvalue),
    }
    rows: list[list[Any]] = [
        ["Group", "N", "Mean", "SD"],
        [str(groups[0]), len(a), fmt_num(a.mean(), 2), fmt_num(a.std(ddof=1) if len(a) > 1 else 0, 2)],
        [str(groups[1]), len(b), fmt_num(b.mean(), 2), fmt_num(b.std(ddof=1) if len(b) > 1 else 0, 2)],
    ]
    summary = [
        ["Statistic", f"t = {fmt_num(res.statistic, 3)}"],
        ["Difference (mean A - mean B)", f"{fmt_num(diff, 3)} (95% CI {fmt_num(ci_lo, 3)} to {fmt_num(ci_hi, 3)})"],
        ["p-value", fmt_num(res.pvalue, 4)],
        ["Method", "Welch's two-sample t-test"],
    ]
    return result, rows, [r[0] for r in summary]


def _wilcoxon_block(df: pd.DataFrame, group_col: str, value_col: str) -> dict[str, Any]:
    groups = df[group_col].dropna().unique().tolist()
    if len(groups) != 2:
        # fall back to Kruskal-Wallis
        arrs = [pd.to_numeric(df.loc[df[group_col] == g, value_col], errors="coerce").dropna().values for g in groups]
        if len(arrs) < 2 or any(len(a) < 1 for a in arrs):
            return _empty_result("kruskal", "n<1 in some group")
        res = stats.kruskal(*arrs)
        return {
            "method": "Kruskal-Wallis",
            "groups": [str(g) for g in groups],
            "n": [int(len(a)) for a in arrs],
            "median": [float(np.median(a)) if len(a) else None for a in arrs],
            "statistic": float(res.statistic),
            "p_value": float(res.pvalue),
        }
    a = pd.to_numeric(df.loc[df[group_col] == groups[0], value_col], errors="coerce").dropna().values
    b = pd.to_numeric(df.loc[df[group_col] == groups[1], value_col], errors="coerce").dropna().values
    if len(a) < 1 or len(b) < 1:
        return _empty_result("Mann-Whitney U", "n<1")
    res = stats.mannwhitneyu(a, b, alternative="two-sided")
    return {
        "method": "Mann-Whitney U (Wilcoxon rank-sum)",
        "groups": [str(g) for g in groups],
        "n": [int(len(a)), int(len(b))],
        "median": [float(np.median(a)), float(np.median(b))],
        "statistic": float(res.statistic),
        "p_value": float(res.pvalue),
    }


def _chi2_or_fisher(df: pd.DataFrame, group_col: str, value_col: str) -> dict[str, Any]:
    ct = pd.crosstab(df[group_col], df[value_col])
    if ct.size == 0:
        return _empty_result("chi2", "empty contingency table")
    use_fisher = ct.shape == (2, 2) and (ct.values < 5).any()
    if use_fisher:
        odds, p = stats.fisher_exact(ct.values)
        return {
            "method": "Fisher's exact test",
            "table": ct.to_dict(),
            "statistic": float(odds),
            "p_value": float(p),
            "odds_ratio": float(odds),
        }
    chi2, p, dof, _exp = stats.chi2_contingency(ct.values, correction=False)
    return {
        "method": "Pearson chi-squared",
        "table": ct.to_dict(),
        "statistic": float(chi2),
        "p_value": float(p),
        "dof": int(dof),
    }


def _empty_result(method: str, reason: str) -> dict[str, Any]:
    return {"method": method, "p_value": None, "statistic": None, "error": reason}


def compare_groups(
    parquet_path: str,
    group_col: str,
    value_col: str,
    test: str = "auto",
    filter_query: str | None = None,
) -> StatBlock:
    df = load_parquet(parquet_path)
    df = filter_df(df, filter_query)
    if group_col not in df.columns or value_col not in df.columns:
        missing = [c for c in (group_col, value_col) if c not in df.columns]
        return StatBlock(
            id=new_stat_id(),
            project_id="",
            analysis_type="inferential",
            title=f"Group comparison: {value_col} by {group_col}",
            params={"parquet_path": parquet_path, "group_col": group_col,
                    "value_col": value_col, "test": test, "filter_query": filter_query},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="",
            source_files=[parquet_path],
            created_at=now_utc(),
            notes=[f"missing columns: {missing}"],
        )

    if test == "auto":
        choice = _pick_test(df, group_col, value_col)
    else:
        choice = test

    if choice == "t":
        result, table_rows, _summary = _ttest_block(df, group_col, value_col)
        title = f"{value_col} 在 {group_col} 各组间的 t 检验"
    elif choice in {"wilcoxon", "mann_whitney", "kruskal"}:
        result = _wilcoxon_block(df, group_col, value_col)
        title = f"{value_col} 在 {group_col} 各组间的非参数检验"
        table_rows = []
    elif choice == "chi2_or_fisher" or choice in {"chi2", "fisher"}:
        result = _chi2_or_fisher(df, group_col, value_col)
        title = f"{value_col} 与 {group_col} 的列联表检验"
        table_rows = []
    else:
        result = _empty_result(choice, "unsupported test")
        title = f"{value_col} 在 {group_col} 各组间的检验"
        table_rows = []

    # Build markdown
    md_parts: list[str] = [f"**{title}**", ""]
    if table_rows:
        md_parts.append(md_table(table_rows[1:], table_rows[0]))
    p_val = result.get("p_value")
    stat = result.get("statistic")
    method = result.get("method", choice)
    md_parts.append("")
    md_parts.append(f"Test: **{method}**")
    if stat is not None:
        md_parts.append(f"Statistic: {fmt_num(stat, 3)}")
    if p_val is not None:
        md_parts.append(f"p-value: {fmt_num(p_val, 4)}")
    if "ci_low" in result and "ci_high" in result:
        md_parts.append(f"95% CI of difference: [{fmt_num(result['ci_low'], 3)}, {fmt_num(result['ci_high'], 3)}]")
    table_md = "\n".join(md_parts)

    return StatBlock(
        id=new_stat_id(),
        project_id="",
        analysis_type="inferential",
        title=title,
        params={
            "parquet_path": parquet_path,
            "group_col": group_col,
            "value_col": value_col,
            "test": test,
            "chosen_test": choice,
            "filter_query": filter_query,
        },
        result_json=jsonable_dict(result),
        markdown_table=table_md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"test={choice}"],
    )
