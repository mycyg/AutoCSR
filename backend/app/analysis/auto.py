"""Auto-analysis router — single-shot trigger that scans processed/ parquets
and dispatches the relevant baseline / safety / survival analyses.

Detection heuristic mirrors the structured_worker's `_detect_adam_kind` but
operates on the *processed* parquet (post-cleansing) so column names may have
been renamed. We tolerate that by tolerating uppercase/lowercase comparison
and by accepting close matches.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.analysis import descriptive, safety, survival
from app.analysis.store import save as save_block
from app.config import data_dir
from app.schemas.stats import StatBlock

logger = logging.getLogger("autocsr.analysis.auto")


@dataclass
class AutoAnalysisReport:
    parquet_path: str
    detected_kind: str | None
    n_blocks_created: int
    notes: list[str]


def _processed_dir(project_id: str) -> Path:
    return data_dir() / "projects" / project_id / "processed"


def _cols_upper(df: pd.DataFrame) -> set[str]:
    return {str(c).upper() for c in df.columns}


def detect_adam_kind(df: pd.DataFrame) -> str | None:
    cols = _cols_upper(df)
    # ADSL: subject-level with subject+trt+demographics
    if "USUBJID" in cols and ("TRT01P" in cols or "TRTP" in cols or "ARM" in cols) and ("AGE" in cols or "SEX" in cols):
        return "ADSL"
    # ADAE: AE per row
    if "USUBJID" in cols and ("AETERM" in cols or "AEDECOD" in cols or "AESOC" in cols):
        return "ADAE"
    # ADTTE: time-to-event
    if "USUBJID" in cols and ("AVAL" in cols and ("CNSR" in cols or "EVNT" in cols or "EVENT" in cols)):
        return "ADTTE"
    # ADEFF: efficacy endpoint per row
    if "USUBJID" in cols and "PARAMCD" in cols and "AVAL" in cols:
        return "ADEFF"
    return None


def _resolve_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    upper_map = {str(c).upper(): str(c) for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.upper() in upper_map:
            return upper_map[cand.upper()]
    return None


def auto_analyze(project_id: str) -> list[StatBlock]:
    """Scan processed/*.parquet, dispatch analyses, return saved StatBlocks."""
    proc = _processed_dir(project_id)
    if not proc.exists():
        return []
    parquets = sorted(proc.glob("*.parquet")) + sorted(proc.glob("*.csv"))
    out: list[StatBlock] = []

    for p in parquets:
        try:
            df = pd.read_parquet(p) if p.suffix.lower() == ".parquet" else pd.read_csv(p, dtype=str, encoding_errors="replace")
        except Exception as e:
            logger.warning("auto_analyze: cannot load %s: %s", p, e)
            continue
        kind = detect_adam_kind(df)
        logger.info("auto_analyze: %s detected_kind=%s rows=%d cols=%d",
                    p.name, kind, df.shape[0], df.shape[1])
        if kind == "ADSL":
            grp = _resolve_col(df, ["TRT01P", "TRTP", "ARM"])
            cont_cols = [c for c in ("AGE", "HEIGHT", "WEIGHT", "BMI")
                         if _resolve_col(df, [c])]
            cont_cols = [_resolve_col(df, [c]) for c in cont_cols if _resolve_col(df, [c])]
            cat_cols = [c for c in ("SEX", "RACE") if _resolve_col(df, [c])]
            cat_cols = [_resolve_col(df, [c]) for c in cat_cols if _resolve_col(df, [c])]
            block = descriptive.baseline_table(
                str(p),
                group_col=grp or "TRT01P",
                cont_cols=cont_cols,
                cat_cols=cat_cols,
            )
            out.append(save_block(project_id, block))
        elif kind == "ADAE":
            soc = _resolve_col(df, ["AESOC", "SOC"]) or "AESOC"
            pt = _resolve_col(df, ["AEDECOD", "AETERM", "PT"]) or "AEDECOD"
            sev = _resolve_col(df, ["AESEV", "AESEVERITY", "SEVERITY"]) or "AESEV"
            rel = _resolve_col(df, ["AEREL", "AERELATED", "CAUSALITY"]) or "AEREL"
            subj = _resolve_col(df, ["USUBJID", "SUBJID", "SUBJECT_ID"]) or "USUBJID"
            grp = _resolve_col(df, ["TRT01P", "TRTP", "ARM"])
            block = safety.ae_summary(
                str(p), soc_col=soc, pt_col=pt, sev_col=sev,
                rel_col=rel, subject_col=subj, group_col=grp,
            )
            out.append(save_block(project_id, block))
        elif kind == "ADTTE":
            t = _resolve_col(df, ["AVAL", "TIME", "DURATION"]) or "AVAL"
            e = _resolve_col(df, ["CNSR", "EVNT", "EVENT"]) or "CNSR"
            grp = _resolve_col(df, ["TRT01P", "TRTP", "ARM"])
            block = survival.km_estimate(str(p), time_col=t, event_col=e, group_col=grp)
            out.append(save_block(project_id, block))
        else:
            # Unrecognized — skip silently
            continue

    logger.info("auto_analyze project=%s created %d blocks", project_id, len(out))
    return out
