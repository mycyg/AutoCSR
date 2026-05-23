"""M21 — Kaplan-Meier curve with at-risk table.

Builds on M14 km_estimate but adds a row of at-risk counts at
configurable time anchors (default 0/3/6/9/12 months). Output is a
StatBlock whose ``result_json`` includes:

    {
      "groups": [{"name": str, "survival": [(t, s), ...]}, ...],
      "risk_table": {"time_points": [...], "rows": [{"group": str, "n_at_risk": [...]}]},
      "logrank_p": float | None,
      "median_survival": {group: float|None}
    }

Plus an embedded matplotlib PNG (data URI) showing the curve + table.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import (
    jsonable_dict, load_parquet, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock

logger = logging.getLogger("autocsr.analysis.km_with_risk")


def _to_event(series: pd.Series, name: str) -> pd.Series:
    num = pd.to_numeric(series, errors="coerce")
    if name.upper() == "CNSR":
        return 1 - num.fillna(1)
    return num.fillna(0)


def _at_risk(times: pd.Series, t: float) -> int:
    return int((times >= t).sum())


def _try_matplotlib_png(groups: list[dict[str, Any]],
                          risk_table: dict[str, Any]) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    try:
        fig = plt.figure(figsize=(7.5, 5.5))
        gs = fig.add_gridspec(2, 1, height_ratios=[3, 1.2], hspace=0.4)
        ax_curve = fig.add_subplot(gs[0])
        ax_table = fig.add_subplot(gs[1])
        ax_table.axis("off")
        for g in groups:
            pts = g.get("survival") or []
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax_curve.step(xs, ys, where="post", label=g.get("name") or "group")
        ax_curve.set_xlabel("Time")
        ax_curve.set_ylabel("Survival probability")
        ax_curve.set_ylim(0, 1.02)
        ax_curve.set_title("Kaplan-Meier survival with at-risk table")
        ax_curve.legend(loc="best", fontsize=8)
        ax_curve.grid(True, alpha=0.3)
        # at-risk table
        time_points = risk_table.get("time_points") or []
        rows = risk_table.get("rows") or []
        if time_points and rows:
            cell_text = [
                [str(g["group"])] + [str(v) for v in g.get("n_at_risk", [])]
                for g in rows
            ]
            col_labels = ["Group"] + [str(t) for t in time_points]
            tbl = ax_table.table(
                cellText=cell_text, colLabels=col_labels, loc="center",
                cellLoc="center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.1)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning("km_risk_png_failed: %s", e)
        return ""


def km_with_risk_table(
    parquet_path: str,
    time_col: str = "AVAL",
    event_col: str = "CNSR",
    group_col: str | None = "TRT01P",
    time_points: list[float] | None = None,
) -> StatBlock:
    if time_points is None:
        time_points = [0, 3, 6, 9, 12]
    df = load_parquet(parquet_path)
    missing = [c for c in (time_col, event_col) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="survival",
            title="KM with risk table",
            params={"parquet_path": parquet_path, "time_col": time_col,
                    "event_col": event_col, "group_col": group_col,
                    "time_points": time_points},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing columns: {missing}"],
        )

    t = pd.to_numeric(df[time_col], errors="coerce")
    e = _to_event(df[event_col], event_col)
    valid = t.notna() & e.notna()
    df2 = df[valid].copy()
    df2["__t__"] = t[valid].astype(float)
    df2["__e__"] = e[valid].astype(int).clip(0, 1)

    groups_out: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    medians: dict[str, Any] = {}
    logrank_p: float | None = None
    notes: list[str] = []

    try:
        from lifelines import KaplanMeierFitter
        from lifelines.statistics import multivariate_logrank_test
        if group_col and group_col in df2.columns:
            unique_groups = sorted(df2[group_col].dropna().unique().tolist(), key=str)
            for g in unique_groups:
                sub = df2[df2[group_col] == g]
                if sub.empty:
                    continue
                kmf = KaplanMeierFitter()
                kmf.fit(sub["__t__"], sub["__e__"], label=str(g))
                sf = kmf.survival_function_
                survival = [(float(idx), float(sf[str(g)].iloc[i]))
                             for i, idx in enumerate(sf.index)]
                groups_out.append({"name": str(g), "survival": survival,
                                    "n_total": int(len(sub))})
                medians[str(g)] = (None if pd.isna(kmf.median_survival_time_)
                                     else float(kmf.median_survival_time_))
                risk_rows.append({
                    "group": str(g),
                    "n_at_risk": [_at_risk(sub["__t__"], tp) for tp in time_points],
                })
            try:
                lr = multivariate_logrank_test(df2["__t__"], df2[group_col], df2["__e__"])
                logrank_p = float(lr.p_value)
            except Exception:
                pass
        else:
            kmf = KaplanMeierFitter()
            kmf.fit(df2["__t__"], df2["__e__"], label="overall")
            sf = kmf.survival_function_
            survival = [(float(idx), float(sf["overall"].iloc[i]))
                         for i, idx in enumerate(sf.index)]
            groups_out.append({"name": "overall", "survival": survival,
                                "n_total": int(len(df2))})
            medians["overall"] = (None if pd.isna(kmf.median_survival_time_)
                                    else float(kmf.median_survival_time_))
            risk_rows.append({
                "group": "overall",
                "n_at_risk": [_at_risk(df2["__t__"], tp) for tp in time_points],
            })
    except ImportError:
        notes.append("lifelines not installed; survival curves omitted")

    risk_table = {"time_points": time_points, "rows": risk_rows}

    # ECharts custom-renderer hint (consumed by KMWithRiskChart.vue)
    echarts_spec = {
        "type": "km_with_risk",
        "groups": [{"name": g["name"], "data": g["survival"]} for g in groups_out],
        "risk_table": risk_table,
    }
    img = _try_matplotlib_png(groups_out, risk_table)
    # Markdown table for downstream citation
    md_lines = ["| Group | n | " + " | ".join(str(t) for t in time_points) + " | Median |",
                 "| --- | --- | " + " | ".join("---" for _ in time_points) + " | --- |"]
    for g, r in zip(groups_out, risk_rows):
        median = medians.get(g["name"])
        md_lines.append(
            f"| {g['name']} | {g.get('n_total', 0)} | "
            + " | ".join(str(v) for v in r["n_at_risk"])
            + " | " + (f"{median:.2f}" if median is not None else "NR") + " |"
        )
    markdown_table = "\n".join(md_lines)

    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="survival",
        title=f"KM with risk table ({time_col})",
        params={"parquet_path": parquet_path, "time_col": time_col,
                "event_col": event_col, "group_col": group_col,
                "time_points": time_points},
        result_json=jsonable_dict({
            "groups": groups_out,
            "risk_table": risk_table,
            "median_survival": medians,
            "logrank_p": logrank_p,
            "image_data_uri": img,
            "echarts_spec": echarts_spec,
        }),
        markdown_table=markdown_table,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=notes,
    )
