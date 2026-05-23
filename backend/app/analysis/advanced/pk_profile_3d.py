"""M21 — 3D PK concentration-time profile (time × concentration × subject)."""
from __future__ import annotations

import base64
import io
import logging
from typing import Any

import numpy as np
import pandas as pd

from app.analysis._common import jsonable_dict, load_parquet, new_stat_id, now_utc
from app.schemas.stats import StatBlock

logger = logging.getLogger("autocsr.analysis.pk_3d")


def _try_png(times: list[float], concs: list[float],
              subjects: list[float], subject_labels: list[str],
              title: str) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except Exception:
        return ""
    try:
        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection="3d")
        sc = ax.scatter(times, subjects, concs, c=concs,
                         cmap="viridis", s=24, alpha=0.7)
        ax.set_xlabel("Time (h)")
        ax.set_ylabel("Subject")
        ax.set_zlabel("Concentration")
        ax.set_title(title)
        fig.colorbar(sc, ax=ax, fraction=0.04, pad=0.06)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
        plt.close(fig)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        logger.warning("pk_3d_png_failed: %s", e)
        return ""


def pk_profile_3d(
    parquet_path: str,
    subject_col: str = "USUBJID",
    time_col: str = "PCDTC",
    conc_col: str = "PCSTRESN",
) -> StatBlock:
    df = load_parquet(parquet_path)
    missing = [c for c in (subject_col, time_col, conc_col) if c not in df.columns]
    if missing:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="custom",
            title="PK profile 3D",
            params={"parquet_path": parquet_path, "subject_col": subject_col,
                    "time_col": time_col, "conc_col": conc_col},
            result_json={"error": f"missing columns: {missing}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing columns: {missing}"],
        )
    df2 = df.copy()
    # Time may be ISO datetime (PCDTC) or numeric (PCTPTNUM). Try datetime
    # first, fall back to numeric.
    t_parsed = pd.to_datetime(df2[time_col], errors="coerce")
    if t_parsed.notna().any():
        t0 = t_parsed.min()
        times = ((t_parsed - t0).dt.total_seconds() / 3600.0).astype(float)
    else:
        times = pd.to_numeric(df2[time_col], errors="coerce").astype(float)
    concs = pd.to_numeric(df2[conc_col], errors="coerce").astype(float)
    subj_raw = df2[subject_col].astype(str)
    subj_unique = sorted(subj_raw.dropna().unique().tolist())
    subj_idx = {s: i for i, s in enumerate(subj_unique)}
    subj_num = subj_raw.map(subj_idx).astype(float)
    valid = times.notna() & concs.notna() & subj_num.notna()
    times = times[valid].tolist()
    concs = concs[valid].tolist()
    subj_num_list = subj_num[valid].tolist()
    subject_labels = subj_unique
    img = _try_png(times, concs, subj_num_list, subject_labels,
                    title=f"PK 3D ({conc_col})")
    md = (
        f"| metric | value |\n| --- | --- |\n"
        f"| n_observations | {len(times)} |\n"
        f"| n_subjects | {len(subject_labels)} |\n"
        f"| t_min_h | {min(times) if times else 'NA'} |\n"
        f"| t_max_h | {max(times) if times else 'NA'} |\n"
        f"| c_min | {min(concs) if concs else 'NA'} |\n"
        f"| c_max | {max(concs) if concs else 'NA'} |\n"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="custom",
        title=f"PK profile 3D ({conc_col})",
        params={"parquet_path": parquet_path, "subject_col": subject_col,
                "time_col": time_col, "conc_col": conc_col},
        result_json=jsonable_dict({
            "n_observations": len(times),
            "subject_labels": subject_labels,
            "image_data_uri": img,
            "echarts_spec": {
                # echarts-gl scatter3D series, fallback to 2D scatter if
                # echarts-gl is unavailable on the client.
                "type": "scatter3D",
                "data": list(zip(times, subj_num_list, concs)),
                "x_axis": "time_h", "y_axis": "subject_idx",
                "z_axis": conc_col,
                "subject_labels": subject_labels,
            },
        }),
        markdown_table=md,
        source_files=[parquet_path],
        created_at=now_utc(), notes=[],
    )
