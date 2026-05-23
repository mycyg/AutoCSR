"""CONSORT participant-flow diagram → StatBlock.

Reads any available ADSL parquet and infers each CONSORT stage from common
SDTM/ADaM flags:

    Screened     — count of rows in ADSL (or ``SCRFL`` if present)
    Randomized   — RANDFL=Y (or SAFFL=Y as fallback)
    Treated      — TRT01A non-null (or TRT01P)
    Completed    — COMPFL=Y (or DCREASCD missing)
    Discontinued — DCREASCD non-null

Output:
    * mermaid graph definition (renderable in the UI)
    * matplotlib PNG fallback
    * markdown table with per-arm counts when TRT01P/A is present
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.analysis._common import (
    jsonable_dict, load_parquet, md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


def _flag_count(df: pd.DataFrame, candidates: list[str], match_y: bool = True) -> int:
    for c in candidates:
        if c in df.columns:
            if match_y:
                return int((df[c].astype(str).str.upper() == "Y").sum())
            return int(df[c].notna().sum())
    return 0


def _build_stages(df: pd.DataFrame) -> dict[str, int]:
    n_total = int(df.shape[0])
    n_screened = _flag_count(df, ["SCRFL"], match_y=True) or n_total
    n_random = _flag_count(df, ["RANDFL", "SAFFL"], match_y=True) or n_total
    n_treated = max(_flag_count(df, ["TRT01A", "TRT01P"], match_y=False),
                     _flag_count(df, ["SAFFL"], match_y=True))
    n_completed = _flag_count(df, ["COMPFL"], match_y=True)
    if n_completed == 0 and "DCREASCD" in df.columns:
        n_completed = int(df["DCREASCD"].isna().sum())
    elif n_completed == 0:
        n_completed = max(0, n_treated)
    n_discontinued = 0
    if "DCREASCD" in df.columns:
        n_discontinued = int(df["DCREASCD"].notna().sum())
    return {
        "screened": n_screened,
        "randomized": n_random,
        "treated": n_treated or n_random,
        "completed": n_completed,
        "discontinued": n_discontinued,
    }


def _per_arm_counts(df: pd.DataFrame) -> list[dict[str, Any]]:
    if "TRT01P" not in df.columns:
        return []
    out = []
    for arm, g in df.groupby("TRT01P", dropna=False, observed=False):
        out.append({
            "arm": str(arm),
            "n_treated": int(g.shape[0]),
            "n_completed": int((g.get("COMPFL", pd.Series(dtype=str))
                                .astype(str).str.upper() == "Y").sum())
                            if "COMPFL" in g.columns else 0,
            "n_discontinued": int(g.get("DCREASCD", pd.Series(dtype=object))
                                    .notna().sum()) if "DCREASCD" in g.columns else 0,
        })
    return out


def _mermaid(stages: dict[str, int], arms: list[dict[str, Any]]) -> str:
    lines = ["graph TD"]
    lines.append(f'  A0["Screened (n={stages["screened"]})"]')
    lines.append(f'  A1["Randomized (n={stages["randomized"]})"]')
    lines.append("  A0 --> A1")
    if arms:
        for i, a in enumerate(arms):
            node = f'B{i}["{a["arm"]} (n={a["n_treated"]})"]'
            lines.append(f"  {node}")
            lines.append(f"  A1 --> B{i}")
            if a["n_completed"] or a["n_discontinued"]:
                lines.append(f'  C{i}["Completed: {a["n_completed"]}\\nDiscontinued: {a["n_discontinued"]}"]')
                lines.append(f"  B{i} --> C{i}")
    else:
        lines.append(f'  A2["Treated (n={stages["treated"]})"]')
        lines.append("  A1 --> A2")
        lines.append(f'  A3["Completed (n={stages["completed"]})"]')
        lines.append(f'  A4["Discontinued (n={stages["discontinued"]})"]')
        lines.append("  A2 --> A3")
        lines.append("  A2 --> A4")
    return "\n".join(lines)


def _save_png(stages: dict[str, int], arms: list[dict[str, Any]],
               out_path: Path) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch
    except Exception:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.axis("off")

    def box(x: float, y: float, w: float, h: float, text: str, color: str = "#dbeafe") -> None:
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05",
                            linewidth=1, edgecolor="#1e3a8a", facecolor=color)
        ax.add_patch(p)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9)

    box(2, 8, 4, 1, f"Screened\nn = {stages['screened']}")
    box(2, 6, 4, 1, f"Randomized\nn = {stages['randomized']}")
    ax.annotate("", xy=(4, 7.0), xytext=(4, 8.0),
                arrowprops=dict(arrowstyle="->", color="#1e3a8a"))
    if arms:
        n = len(arms)
        for i, a in enumerate(arms):
            x = 0.5 + i * (8 / n)
            w = 7 / n
            box(x, 4, w, 1, f"{a['arm']}\nn = {a['n_treated']}", color="#bfdbfe")
            ax.annotate("", xy=(x + w / 2, 5.0), xytext=(4, 6.0),
                         arrowprops=dict(arrowstyle="->", color="#1e3a8a"))
            box(x, 1.5, w, 1.5,
                 f"Completed: {a['n_completed']}\nDiscontinued: {a['n_discontinued']}",
                 color="#fef3c7")
            ax.annotate("", xy=(x + w / 2, 3.0), xytext=(x + w / 2, 4.0),
                         arrowprops=dict(arrowstyle="->", color="#1e3a8a"))
    else:
        box(2, 4, 4, 1, f"Treated\nn = {stages['treated']}", color="#bfdbfe")
        ax.annotate("", xy=(4, 5.0), xytext=(4, 6.0),
                     arrowprops=dict(arrowstyle="->", color="#1e3a8a"))
        box(2, 1.5, 4, 1.5,
             f"Completed: {stages['completed']}\nDiscontinued: {stages['discontinued']}",
             color="#fef3c7")
        ax.annotate("", xy=(4, 3.0), xytext=(4, 4.0),
                     arrowprops=dict(arrowstyle="->", color="#1e3a8a"))

    ax.set_xlim(0, 8); ax.set_ylim(0.5, 9.5)
    ax.set_title("CONSORT participant flow", fontsize=11)
    fig.savefig(str(out_path), dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out_path


def consort_flow(
    parquet_paths: list[str],
    *,
    output_dir: str | None = None,
) -> StatBlock:
    # Pick the parquet that looks most like ADSL (rows ≤ subjects)
    target: pd.DataFrame | None = None
    chosen_path: str | None = None
    for p in parquet_paths:
        try:
            df = load_parquet(p)
        except Exception:
            continue
        score = 0
        for col in ("USUBJID", "RANDFL", "SAFFL", "TRT01P", "COMPFL", "DCREASCD"):
            if col in df.columns:
                score += 1
        if target is None or score > 0:
            target, chosen_path = df, p
            if score >= 2:
                break
    if target is None or chosen_path is None:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="consort",
            title="CONSORT 流程", params={"parquet_paths": parquet_paths},
            result_json={"error": "no readable parquet for ADSL inference"},
            markdown_table="", source_files=list(parquet_paths),
            created_at=now_utc(),
        )

    stages = _build_stages(target)
    arms = _per_arm_counts(target)
    mermaid = _mermaid(stages, arms)

    out_dir = Path(output_dir) if output_dir else Path(".") / "_consort_out"
    png = _save_png(stages, arms, out_dir / f"consort_{new_stat_id()}.png")

    rows = [
        ["Screened", stages["screened"]],
        ["Randomized", stages["randomized"]],
        ["Treated", stages["treated"]],
        ["Completed", stages["completed"]],
        ["Discontinued", stages["discontinued"]],
    ]
    table_md = md_table(rows, ["Stage", "N"])
    md = (
        "**CONSORT participant flow**\n\n"
        + table_md
        + "\n\n```mermaid\n"
        + mermaid
        + "\n```\n"
        + (f"\n*PNG fallback:* `{png.name}`" if png else "")
    )
    result_json = jsonable_dict({
        "stages": stages, "arms": arms,
        "mermaid": mermaid, "png_path": str(png) if png else None,
        "source_parquet": chosen_path,
    })
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="consort",
        title="CONSORT 受试者流程", params={"parquet_paths": parquet_paths},
        result_json=result_json, markdown_table=md,
        source_files=[chosen_path], created_at=now_utc(),
        notes=[f"arms={len(arms)}", f"png={'yes' if png else 'no'}"],
    )
