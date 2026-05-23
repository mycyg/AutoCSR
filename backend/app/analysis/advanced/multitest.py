"""Multiple-comparison correction → StatBlock.

Wraps ``statsmodels.stats.multitest.multipletests`` and renders a markdown
table that pairs raw p with adjusted p plus a significance star.

Public API:
    multitest_adjust(p_values, method='fdr_bh', labels=None, alpha=0.05)
        -> StatBlock
"""
from __future__ import annotations

from typing import Any

from app.analysis._common import jsonable_dict, md_table, new_stat_id, now_utc
from app.schemas.stats import StatBlock


_METHOD_LABELS: dict[str, str] = {
    "bonferroni": "Bonferroni",
    "holm": "Holm",
    "hochberg": "Hochberg",
    "fdr_bh": "Benjamini-Hochberg (FDR)",
    "fdr_by": "Benjamini-Yekutieli (FDR)",
}


def _sig_mark(p: float, alpha: float) -> str:
    if p < alpha / 100:
        return "***"
    if p < alpha / 10:
        return "**"
    if p < alpha:
        return "*"
    return ""


def multitest_adjust(
    p_values: list[float],
    method: str = "fdr_bh",
    labels: list[str] | None = None,
    alpha: float = 0.05,
) -> StatBlock:
    if not p_values:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="multitest",
            title="多重比较校正", params={"method": method, "alpha": alpha},
            result_json={"error": "no p-values provided"},
            markdown_table="", source_files=[], created_at=now_utc(),
        )

    method = method.lower().strip()
    if method not in _METHOD_LABELS:
        method = "fdr_bh"
    labels = labels or [f"Test {i+1}" for i in range(len(p_values))]
    if len(labels) != len(p_values):
        labels = (labels + [f"Test {i+1}" for i in range(len(p_values))])[:len(p_values)]

    try:
        from statsmodels.stats.multitest import multipletests
    except Exception:
        # Fallback: just emit Bonferroni manually
        adj = [min(1.0, p * len(p_values)) for p in p_values]
        reject = [p < alpha for p in adj]
        method = "bonferroni"
    else:
        reject_arr, adj_arr, _, _ = multipletests(p_values, alpha=alpha, method=method)
        adj = [float(x) for x in adj_arr]
        reject = [bool(x) for x in reject_arr]

    rows: list[list[Any]] = [
        [labels[i], f"{p_values[i]:.4f}", f"{adj[i]:.4f}",
         "Yes" if reject[i] else "No",
         _sig_mark(adj[i], alpha)]
        for i in range(len(p_values))
    ]
    headers = ["Test", "Raw p", "Adjusted p", f"Reject at α={alpha}", "Significance"]
    table_md = md_table(rows, headers)

    full_md = (
        f"**多重比较校正 — {_METHOD_LABELS.get(method, method)}**\n\n"
        + table_md
        + f"\n\nMethod: **{_METHOD_LABELS.get(method, method)}**; "
        + f"α = {alpha}; total tests = {len(p_values)}; "
        + f"rejected = {sum(reject)}"
    )

    result_json = jsonable_dict({
        "method": method,
        "alpha": alpha,
        "raw_p": list(map(float, p_values)),
        "adjusted_p": adj,
        "reject": reject,
        "labels": labels,
        "n_tests": len(p_values),
        "n_rejected": int(sum(reject)),
    })

    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="multitest",
        title=f"多重比较校正（{_METHOD_LABELS.get(method, method)}）",
        params={"method": method, "alpha": alpha, "labels": labels},
        result_json=result_json,
        markdown_table=full_md, source_files=[], created_at=now_utc(),
        notes=[f"n_tests={len(p_values)}", f"n_rejected={sum(reject)}"],
    )
