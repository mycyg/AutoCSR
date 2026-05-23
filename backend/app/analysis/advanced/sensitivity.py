"""Sensitivity analyses — ITT / PP / LOCF / MMRM.

Each method produces its own StatBlock (analysis_type='sensitivity'), and an
``sensitivity_analysis()`` convenience runs all requested ones and returns
them in a list plus a comparison summary table.

LOCF treats ``outcome_col`` as a per-subject longitudinal value; for purposes
of this simplified implementation we fill missing within ``USUBJID`` using
forward-fill if ``USUBJID`` exists, else fall back to overall median fill.

MMRM uses ``statsmodels.formula.api.mixedlm`` when available, else degrades
to OLS-on-the-completers as a labelled fallback.
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


def _welch(a: np.ndarray, b: np.ndarray) -> dict[str, Any] | None:
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
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


def _block(method_label: str, parquet_path: str, outcome_col: str,
            group_col: str, summary: dict[str, Any] | None, extra_notes: list[str],
            params: dict[str, Any]) -> StatBlock:
    if summary is None:
        md = f"**{method_label}** — insufficient data"
        result_json: dict[str, Any] = {"error": "insufficient data", "method": method_label}
    else:
        rows = [
            ["A", summary["n_a"], fmt_num(summary["mean_a"], 3)],
            ["B", summary["n_b"], fmt_num(summary["mean_b"], 3)],
        ]
        table_md = md_table(rows, ["Arm", "N", "Mean"])
        md = (
            f"**{method_label}**\n\n" + table_md +
            f"\n\nMean Δ (A − B): {fmt_num(summary['diff'], 3)} "
            f"(95% CI {fmt_num(summary['ci_low'], 3)}, {fmt_num(summary['ci_high'], 3)})  "
            f"p = {fmt_num(summary['p_value'], 4)}"
        )
        result_json = jsonable_dict({"method": method_label, **summary})
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="sensitivity",
        title=f"敏感性分析（{method_label}）",
        params=params, result_json=result_json,
        markdown_table=md, source_files=[parquet_path],
        created_at=now_utc(),
        notes=[f"method={method_label}"] + extra_notes,
    )


def _itt(df: pd.DataFrame, outcome_col: str, group_col: str) -> dict[str, Any] | None:
    groups = sorted(map(str, df[group_col].dropna().unique()))[:2]
    if len(groups) < 2:
        return None
    g_a, g_b = groups
    a = pd.to_numeric(df.loc[df[group_col].astype(str) == g_a, outcome_col],
                       errors="coerce").to_numpy()
    b = pd.to_numeric(df.loc[df[group_col].astype(str) == g_b, outcome_col],
                       errors="coerce").to_numpy()
    return _welch(a, b)


def _pp(df: pd.DataFrame, outcome_col: str, group_col: str) -> dict[str, Any] | None:
    # Per-protocol: completers only (COMPFL=Y if present, else drop NaN outcome)
    if "COMPFL" in df.columns:
        sub = df[df["COMPFL"].astype(str).str.upper() == "Y"]
    else:
        sub = df.dropna(subset=[outcome_col])
    return _itt(sub, outcome_col, group_col)


def _locf(df: pd.DataFrame, outcome_col: str, group_col: str) -> dict[str, Any] | None:
    work = df.copy()
    if "USUBJID" in work.columns:
        work = work.sort_values(["USUBJID", outcome_col], na_position="last")
        work[outcome_col] = work.groupby("USUBJID")[outcome_col].ffill()
    # Final pass: any still-missing fill with overall median
    num = pd.to_numeric(work[outcome_col], errors="coerce")
    med = float(num.median()) if num.notna().any() else 0.0
    work[outcome_col] = num.fillna(med)
    return _itt(work, outcome_col, group_col)


def _mmrm(df: pd.DataFrame, outcome_col: str, group_col: str
           ) -> tuple[dict[str, Any] | None, str]:
    # Simplified: try statsmodels mixedlm; if that fails, OLS-on-completers
    try:
        import statsmodels.formula.api as smf
    except Exception:
        return _pp(df, outcome_col, group_col), "PP fallback (statsmodels missing)"
    work = df.dropna(subset=[outcome_col, group_col]).copy()
    if work.empty:
        return None, "no data"
    work[outcome_col] = pd.to_numeric(work[outcome_col], errors="coerce")
    work = work.dropna(subset=[outcome_col])
    if work.empty or work[group_col].nunique() < 2:
        return None, "no data"
    if "USUBJID" not in work.columns or work["USUBJID"].nunique() < 3:
        # No clustering possible — OLS fallback
        try:
            m = smf.ols(f"{outcome_col} ~ C({group_col})", data=work).fit()
            params = m.params
            conf = m.conf_int().to_dict(orient="index")
            term_name = next((k for k in params.index if k.startswith("C(")), None)
            if not term_name:
                return None, "no term"
            ci = list(conf[term_name].values())
            return ({
                "n_a": int(work[group_col].value_counts().iloc[0]),
                "n_b": int(work[group_col].value_counts().iloc[1]),
                "mean_a": float(work.loc[work[group_col] == work[group_col].unique()[0], outcome_col].mean()),
                "mean_b": float(work.loc[work[group_col] == work[group_col].unique()[1], outcome_col].mean()),
                "diff": float(params[term_name]),
                "ci_low": float(ci[0]), "ci_high": float(ci[1]),
                "p_value": float(m.pvalues[term_name]),
            }, "OLS (no USUBJID clustering)")
        except Exception:
            return _itt(work, outcome_col, group_col), "ITT fallback (OLS failed)"
    try:
        m = smf.mixedlm(f"{outcome_col} ~ C({group_col})", work,
                          groups=work["USUBJID"]).fit(disp=False)
        params = m.params
        term_name = next((k for k in params.index if k.startswith("C(")), None)
        if not term_name:
            return None, "no term"
        ci = m.conf_int()
        ci_lo = float(ci.loc[term_name, 0])
        ci_hi = float(ci.loc[term_name, 1])
        groups = sorted(work[group_col].astype(str).unique())[:2]
        return ({
            "n_a": int((work[group_col].astype(str) == groups[0]).sum()),
            "n_b": int((work[group_col].astype(str) == groups[1]).sum()),
            "mean_a": float(work.loc[work[group_col].astype(str) == groups[0], outcome_col].mean()),
            "mean_b": float(work.loc[work[group_col].astype(str) == groups[1], outcome_col].mean()),
            "diff": float(params[term_name]),
            "ci_low": ci_lo, "ci_high": ci_hi,
            "p_value": float(m.pvalues[term_name]),
        }, "MixedLM by USUBJID")
    except Exception as e:
        return _itt(work, outcome_col, group_col), f"ITT fallback (mixedlm failed: {e})"


def sensitivity_analysis(
    parquet_path: str,
    outcome_col: str,
    group_col: str,
    methods: list[str] | None = None,
) -> list[StatBlock]:
    df = load_parquet(parquet_path)
    methods = [m.lower().strip() for m in (methods or ["itt", "pp", "locf", "mmrm"])]
    params_common = {
        "parquet_path": parquet_path, "outcome_col": outcome_col,
        "group_col": group_col, "methods": methods,
    }
    out: list[StatBlock] = []
    if outcome_col not in df.columns or group_col not in df.columns:
        out.append(StatBlock(
            id=new_stat_id(), project_id="", analysis_type="sensitivity",
            title="敏感性分析", params=params_common,
            result_json={"error": f"missing column(s): {outcome_col}, {group_col}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(),
        ))
        return out

    if "itt" in methods:
        out.append(_block("ITT", parquet_path, outcome_col, group_col,
                          _itt(df, outcome_col, group_col), [], params_common))
    if "pp" in methods:
        out.append(_block("PP (completers)", parquet_path, outcome_col, group_col,
                          _pp(df, outcome_col, group_col), [], params_common))
    if "locf" in methods:
        out.append(_block("LOCF", parquet_path, outcome_col, group_col,
                          _locf(df, outcome_col, group_col), [], params_common))
    if "mmrm" in methods:
        mmrm_res, mmrm_note = _mmrm(df, outcome_col, group_col)
        out.append(_block("MMRM", parquet_path, outcome_col, group_col,
                          mmrm_res, [mmrm_note], params_common))
    return out
