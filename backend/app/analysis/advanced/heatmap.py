"""M21 — gene / biomarker heatmap (long format → pivot)."""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import jsonable_dict, load_parquet, new_stat_id, now_utc
from app.schemas.stats import StatBlock

logger = logging.getLogger("autocsr.analysis.heatmap")


def _try_png(matrix: np.ndarray, row_labels: list[str],
              col_labels: list[str], title: str) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    try:
        h = max(3.0, min(10.0, 0.25 * len(row_labels) + 1.5))
        w = max(4.0, min(12.0, 0.30 * len(col_labels) + 2.0))
        fig, ax = plt.subplots(figsize=(w, h))
        im = ax.imshow(matrix, aspect="auto", cmap="RdYlBu_r", interpolation="nearest")
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, rotation=60, ha="right", fontsize=7)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=7)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning("heatmap_png_failed: %s", e)
        return ""


def heatmap(
    parquet_path: str,
    row_col: str,
    col_col: str,
    value_col: str,
    aggfunc: str = "mean",
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in (row_col, col_col, value_col) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="custom",
            title="Heatmap",
            params={"parquet_path": parquet_path, "row_col": row_col,
                    "col_col": col_col, "value_col": value_col,
                    "aggfunc": aggfunc},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing columns: {missing}"],
        )
    df2 = df.copy()
    df2[value_col] = pd.to_numeric(df2[value_col], errors="coerce")
    pivot = df2.pivot_table(
        index=row_col, columns=col_col, values=value_col,
        aggfunc=aggfunc,
    )
    row_labels = [str(x) for x in pivot.index.tolist()]
    col_labels = [str(x) for x in pivot.columns.tolist()]
    matrix = pivot.fillna(0).values.astype(float)
    img = _try_png(matrix, row_labels, col_labels,
                    title=f"Heatmap of {value_col}")
    # ECharts heatmap requires [colIdx, rowIdx, value] triples
    echarts_data: list[list[Any]] = []
    for i, r in enumerate(row_labels):
        for j, c in enumerate(col_labels):
            echarts_data.append([j, i, float(matrix[i][j])])
    md = (
        f"| metric | value |\n| --- | --- |\n"
        f"| n_rows | {len(row_labels)} |\n"
        f"| n_cols | {len(col_labels)} |\n"
        f"| min | {float(matrix.min()) if matrix.size else 'NA'} |\n"
        f"| max | {float(matrix.max()) if matrix.size else 'NA'} |\n"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="custom",
        title=f"Heatmap ({row_col} × {col_col})",
        params={"parquet_path": parquet_path, "row_col": row_col,
                "col_col": col_col, "value_col": value_col, "aggfunc": aggfunc},
        result_json=jsonable_dict({
            "row_labels": row_labels,
            "col_labels": col_labels,
            "matrix": matrix.tolist(),
            "image_data_uri": img,
            "echarts_spec": {
                "type": "heatmap",
                "x_labels": col_labels,
                "y_labels": row_labels,
                "data": echarts_data,
                "min": float(matrix.min()) if matrix.size else 0.0,
                "max": float(matrix.max()) if matrix.size else 1.0,
            },
        }),
        markdown_table=md,
        source_files=[parquet_path],
        created_at=now_utc(), notes=[],
    )
