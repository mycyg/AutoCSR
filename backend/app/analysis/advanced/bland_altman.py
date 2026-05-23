"""M21 — Bland-Altman agreement analysis (two measurement methods)."""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import jsonable_dict, load_parquet, new_stat_id, now_utc
from app.schemas.stats import StatBlock

logger = logging.getLogger("autocsr.analysis.bland_altman")


def _try_png(x_mean: list[float], y_diff: list[float],
              bias: float, lo: float, hi: float) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    try:
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        ax.scatter(x_mean, y_diff, alpha=0.6, s=20, color="#0066cc")
        ax.axhline(bias, color="#333", linestyle="-", linewidth=1, label=f"bias={bias:.3f}")
        ax.axhline(hi, color="red", linestyle="--", linewidth=1, label=f"+1.96 SD={hi:.3f}")
        ax.axhline(lo, color="red", linestyle="--", linewidth=1, label=f"-1.96 SD={lo:.3f}")
        ax.set_xlabel("Mean of two methods")
        ax.set_ylabel("Difference (method1 - method2)")
        ax.set_title("Bland-Altman plot")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning("bland_altman_png_failed: %s", e)
        return ""


def bland_altman(
    parquet_path: str,
    col_method1: str,
    col_method2: str,
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in (col_method1, col_method2) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="custom",
            title="Bland-Altman",
            params={"parquet_path": parquet_path, "col_method1": col_method1,
                    "col_method2": col_method2},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing columns: {missing}"],
        )
    a = pd.to_numeric(df[col_method1], errors="coerce")
    b = pd.to_numeric(df[col_method2], errors="coerce")
    valid = a.notna() & b.notna()
    a, b = a[valid].astype(float), b[valid].astype(float)
    if len(a) == 0:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="custom",
            title="Bland-Altman",
            params={"parquet_path": parquet_path, "col_method1": col_method1,
                    "col_method2": col_method2},
            result_json={"error": "no valid paired observations"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=["empty"],
        )
    diff = (a - b).values
    mean = ((a + b) / 2.0).values
    bias = float(diff.mean())
    sd = float(diff.std(ddof=1)) if len(diff) > 1 else 0.0
    lo = bias - 1.96 * sd
    hi = bias + 1.96 * sd
    img = _try_png(mean.tolist(), diff.tolist(), bias, lo, hi)
    md = (
        f"| metric | value |\n| --- | --- |\n"
        f"| n_pairs | {len(diff)} |\n"
        f"| bias | {bias:.4f} |\n"
        f"| sd_of_diff | {sd:.4f} |\n"
        f"| upper_LoA (+1.96 SD) | {hi:.4f} |\n"
        f"| lower_LoA (-1.96 SD) | {lo:.4f} |\n"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="custom",
        title=f"Bland-Altman ({col_method1} vs {col_method2})",
        params={"parquet_path": parquet_path, "col_method1": col_method1,
                "col_method2": col_method2},
        result_json=jsonable_dict({
            "n_pairs": int(len(diff)),
            "bias": bias,
            "sd_of_diff": sd,
            "upper_LoA": hi,
            "lower_LoA": lo,
            "mean_values": mean.tolist(),
            "diff_values": diff.tolist(),
            "image_data_uri": img,
            "echarts_spec": {
                "type": "bland_altman",
                "scatter": list(zip(mean.tolist(), diff.tolist())),
                "bias": bias, "upper_LoA": hi, "lower_LoA": lo,
            },
        }),
        markdown_table=md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=[],
    )
