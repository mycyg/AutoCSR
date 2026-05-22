"""Safety analysis — AE summary by SOC / PT, with severity & relatedness.

Public API:

    ae_summary(parquet_path,
               soc_col='AESOC', pt_col='AEDECOD',
               sev_col='AESEV', rel_col='AEREL',
               subject_col='USUBJID', group_col=None) -> StatBlock

Output structure:
    - Per SOC: n_events / n_subjects (distinct USUBJID) / pct of total subjects
    - Per PT under each SOC: same columns
    - Severity breakdown: mild / moderate / severe rows
    - Relatedness: any AE classed as Possibly/Probably/Definitely related
    - When group_col present: columns split per group
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.analysis._common import (
    fmt_pct, jsonable_dict, load_parquet,
    md_table, new_stat_id, now_utc,
)
from app.schemas.stats import StatBlock


SEVERITY_LIGHT = {"mild", "light", "1", "轻", "轻度"}
SEVERITY_MOD = {"moderate", "med", "2", "中", "中度"}
SEVERITY_SEVERE = {"severe", "sev", "3", "重", "重度"}

REL_RELATED = {
    "related", "definitely related", "probably related", "possibly related",
    "definite", "probable", "possible",
    "有关", "可能有关", "很可能有关", "肯定有关",
}


def _norm(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).strip().lower()


def _severity_label(v: Any) -> str | None:
    n = _norm(v)
    if n in SEVERITY_LIGHT:
        return "Mild"
    if n in SEVERITY_MOD:
        return "Moderate"
    if n in SEVERITY_SEVERE:
        return "Severe"
    return None


def _is_related(v: Any) -> bool:
    return _norm(v) in REL_RELATED


def ae_summary(
    parquet_path: str,
    soc_col: str = "AESOC",
    pt_col: str = "AEDECOD",
    sev_col: str = "AESEV",
    rel_col: str = "AEREL",
    subject_col: str = "USUBJID",
    group_col: str | None = None,
) -> StatBlock:
    df = load_parquet(parquet_path)
    notes: list[str] = []
    present = {
        "soc": soc_col in df.columns,
        "pt": pt_col in df.columns,
        "sev": sev_col in df.columns,
        "rel": rel_col in df.columns,
        "subj": subject_col in df.columns,
    }
    if not present["subj"]:
        return StatBlock(
            id=new_stat_id(), project_id="", analysis_type="safety",
            title="AE summary",
            params={"parquet_path": parquet_path, "soc_col": soc_col,
                    "pt_col": pt_col, "sev_col": sev_col, "rel_col": rel_col,
                    "subject_col": subject_col, "group_col": group_col},
            result_json={"error": f"missing subject column {subject_col}"},
            markdown_table="", source_files=[parquet_path],
            created_at=now_utc(), notes=[f"missing {subject_col}"],
        )

    # Grouping
    if group_col and group_col in df.columns:
        groups = sorted(df[group_col].dropna().unique().tolist(), key=str)
        group_names = [str(g) for g in groups]
        group_dfs = [df[df[group_col].astype(str) == g] for g in group_names]
        denoms = [int(g[subject_col].dropna().nunique()) for g in group_dfs]
    else:
        group_names = ["All Subjects"]
        group_dfs = [df]
        denoms = [int(df[subject_col].dropna().nunique())]
    total_subjects = int(df[subject_col].dropna().nunique())
    notes.append(f"n_subjects_total={total_subjects}")

    def _ev_subj(sub: pd.DataFrame, mask: pd.Series | None = None) -> tuple[int, int]:
        s = sub if mask is None else sub[mask]
        n_events = int(s.shape[0])
        n_subj = int(s[subject_col].dropna().nunique()) if subject_col in s.columns else 0
        return n_events, n_subj

    # Headline: Overall + severity + related
    overview_rows: list[list[Any]] = []

    def _row(label: str, mask_fn) -> list[Any]:
        out_row: list[Any] = [label]
        for g_df, den in zip(group_dfs, denoms):
            mask = mask_fn(g_df) if not g_df.empty else pd.Series(dtype=bool)
            n_ev, n_subj = _ev_subj(g_df, mask)
            cell = f"{n_ev} / {n_subj} ({fmt_pct(n_subj, den)}%)" if den > 0 else f"{n_ev} / 0"
            out_row.append(cell)
        return out_row

    overview_rows.append(_row("**Any AE**", lambda g: g.index.notna()))
    if present["sev"]:
        for level in ("Severe", "Moderate", "Mild"):
            overview_rows.append(_row(
                f"&nbsp;&nbsp;{level}",
                lambda g, level=level: g[sev_col].map(_severity_label) == level,
            ))
    if present["rel"]:
        overview_rows.append(_row("Related AE", lambda g: g[rel_col].map(_is_related)))

    overview_headers = ["Category"] + [f"{g} (N={n})" for g, n in zip(group_names, denoms)]
    overview_md = md_table(overview_rows, overview_headers)

    # SOC / PT breakdown
    soc_rows: list[list[Any]] = []
    soc_data: list[dict[str, Any]] = []
    if present["soc"]:
        socs = sorted({str(v) for v in df[soc_col].dropna().unique()}, key=str)
        for soc in socs:
            soc_row: list[Any] = [f"**{soc}**"]
            soc_info: dict[str, Any] = {"name": soc, "by_group": [], "pts": []}
            for gi, (g_df, den) in enumerate(zip(group_dfs, denoms)):
                mask = g_df[soc_col].astype(str) == soc
                n_ev, n_subj = _ev_subj(g_df, mask)
                cell = f"{n_ev} / {n_subj} ({fmt_pct(n_subj, den)}%)" if den > 0 else f"{n_ev} / 0"
                soc_row.append(cell)
                soc_info["by_group"].append({"group": str(group_names[gi]),
                                              "n_events": n_ev, "n_subjects": n_subj, "denom": den})
            soc_rows.append(soc_row)

            if present["pt"]:
                pts = sorted({str(v) for v in df.loc[df[soc_col].astype(str) == soc, pt_col].dropna().unique()},
                             key=str)
                for pt in pts:
                    pt_row: list[Any] = [f"&nbsp;&nbsp;{pt}"]
                    pt_info: dict[str, Any] = {"name": pt, "by_group": []}
                    for gi, (g_df, den) in enumerate(zip(group_dfs, denoms)):
                        mask = (g_df[soc_col].astype(str) == soc) & (g_df[pt_col].astype(str) == pt)
                        n_ev, n_subj = _ev_subj(g_df, mask)
                        cell = f"{n_ev} / {n_subj} ({fmt_pct(n_subj, den)}%)" if den > 0 else f"{n_ev} / 0"
                        pt_row.append(cell)
                        pt_info["by_group"].append({"group": str(group_names[gi]),
                                                     "n_events": n_ev, "n_subjects": n_subj, "denom": den})
                    soc_rows.append(pt_row)
                    soc_info["pts"].append(pt_info)
            soc_data.append(soc_info)

    soc_md = md_table(soc_rows, overview_headers) if soc_rows else "_SOC column not available_"

    # Total events
    total_events = int(df.shape[0])

    full_md = (
        "**Overall AE incidence (events / subjects)**\n\n"
        + overview_md
        + "\n\n**By SOC / PT**\n\n"
        + soc_md
        + f"\n\nTotal AE events recorded: {total_events}; total subjects exposed: {total_subjects}"
    )

    result_json: dict[str, Any] = jsonable_dict({
        "group_col": group_col if group_col and group_col in df.columns else None,
        "group_names": group_names,
        "denoms": denoms,
        "n_events_total": total_events,
        "n_subjects_total": total_subjects,
        "presence": present,
        "socs": soc_data,
    })

    title = (
        f"不良事件汇总（按 {group_col} 分组，SOC/PT）"
        if group_col and group_col in df.columns
        else "不良事件汇总（SOC/PT）"
    )
    return StatBlock(
        id=new_stat_id(), project_id="", analysis_type="safety",
        title=title,
        params={"parquet_path": parquet_path, "soc_col": soc_col, "pt_col": pt_col,
                "sev_col": sev_col, "rel_col": rel_col,
                "subject_col": subject_col, "group_col": group_col},
        result_json=result_json,
        markdown_table=full_md,
        source_files=[parquet_path],
        created_at=now_utc(),
        notes=notes,
    )
