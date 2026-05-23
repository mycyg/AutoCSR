"""map_to_cdisc proposal generator + transformer apply.

Goals:
  * Detect columns whose name / sample values suggest controlled-vocabulary
    coding (AETERM → MedDRA PT, CMTRT → WHODrug, DIAGNOSIS → ICD-10).
  * For each unique non-null term in the column, fetch top-K candidates from
    the appropriate dictionary; package them into a single CleansingProposal
    with all candidates embedded in ``parameters.mappings``.
  * The transformer reads ``params.user_selections`` (set by the UI when the
    user picks one candidate per term) and writes two new columns to the
    DataFrame: ``<col>_CODE`` and ``<col>_PT``.

This module does NOT call LLMs — pure dictionary lookup.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.coding import dictionary
from app.schemas.cleansing import CleansingProposal
from app.schemas.ingest import DataProfile, IngestResult


# Map column-name patterns → suggested dictionary system.
_NAME_HINTS: list[tuple[str, str]] = [
    ("aeterm", "MEDDRA"),
    ("aedecod", "MEDDRA"),
    ("ae_pt", "MEDDRA"),
    ("cmtrt", "WHODRUG"),
    ("cmdecod", "WHODRUG"),
    ("concomitant", "WHODRUG"),
    ("medication", "WHODRUG"),
    ("drug_name", "WHODRUG"),
    ("diagnosis", "ICD10"),
    ("mhterm", "ICD10"),
    ("mhdecod", "ICD10"),
    ("icd", "ICD10"),
    ("labtest", "LOINC"),
    ("lbtest", "LOINC"),
    ("loinc", "LOINC"),
    ("atc", "ATC"),
    ("snomed", "SNOMED"),
    ("sct", "SNOMED"),
]


def _system_for_column(col_name: str) -> str | None:
    n = (col_name or "").lower()
    if not n:
        return None
    for pat, sys_id in _NAME_HINTS:
        if pat in n:
            return sys_id
    return None


def _unique_terms_from_profile(col_profile: Any) -> list[str]:
    """Pick a deduped list of representative terms from a column profile."""
    out: list[str] = []
    seen: set[str] = set()
    samples = list(getattr(col_profile, "sample_values", []) or [])
    for tup in (getattr(col_profile, "top_freq", []) or []):
        if isinstance(tup, (list, tuple)) and len(tup) >= 1:
            samples.append(tup[0])
    for s in samples:
        if s is None:
            continue
        sv = str(s).strip()
        if not sv or sv.lower() in ("nan", "none", "null", "na", "<na>", "<redacted>"):
            continue
        if sv in seen:
            continue
        seen.add(sv)
        out.append(sv)
    return out


def build_proposals(profile: DataProfile, ingest: IngestResult,
                    *, top_k: int = 3) -> list[CleansingProposal]:
    """Generate one map_to_cdisc proposal per column that looks codable."""
    out: list[CleansingProposal] = []
    for col in profile.columns:
        sys_id = _system_for_column(col.name)
        if not sys_id:
            continue
        info = dictionary.get_system_info(sys_id)
        if info is None or not info.available:
            # Skip silently rather than dropping a broken proposal; UI surfaces
            # availability via /coding/systems.
            continue
        terms = _unique_terms_from_profile(col)
        if not terms:
            continue
        mappings: list[dict[str, Any]] = []
        for t in terms:
            cands = dictionary.lookup(sys_id, t, top_k=top_k)
            mappings.append({
                "original": t,
                "candidates": [c.model_dump() for c in cands],
            })
        if not mappings:
            continue
        # Suggest auto-accepts for high-confidence top picks
        auto_high = sum(1 for m in mappings
                        if m["candidates"] and float(m["candidates"][0]["score"]) >= 0.9)
        rationale = (
            f"列 `{col.name}` 看起来需要映射到 {sys_id}；"
            f"已为 {len(mappings)} 个 unique term 各取 top {top_k} 候选；"
            f"其中 {auto_high} 个 confidence ≥0.9 可批量接受。"
        )
        out.append(CleansingProposal(
            id=uuid.uuid4().hex[:12],
            project_id=ingest.project_id, file_id=ingest.file_id,
            sheet=profile.sheet, type="map_to_cdisc",
            target_columns=[col.name],
            parameters={
                "system": sys_id,
                "top_k": top_k,
                "mappings": mappings,
                "code_col_suffix": "_CODE",
                "pt_col_suffix": "_PT",
                # user_selections will be filled by the UI:
                #   {"<original term>": "<chosen code>"}
                "user_selections": {},
            },
            rationale=rationale,
            confidence=0.7 if auto_high else 0.55,
            impact_rows=profile.n_rows,
            created_at=datetime.now(timezone.utc),
        ))
    return out


def apply_map_to_cdisc(df: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    """Apply user-chosen mappings — add ``<col>_CODE`` and ``<col>_PT`` columns.

    If the user hasn't selected anything, auto-pick the top candidate when its
    score ≥0.9; otherwise leave the cell NaN so reviewers know it's pending.
    """
    cols = params.get("target_columns") or []
    if not cols:
        return df
    col = cols[0] if isinstance(cols, list) else cols
    if col not in df.columns:
        return df
    mappings = params.get("mappings") or []
    selections: dict[str, str] = dict(params.get("user_selections") or {})
    suffix_code = params.get("code_col_suffix", "_CODE")
    suffix_pt = params.get("pt_col_suffix", "_PT")

    code_map: dict[str, str] = {}
    pt_map: dict[str, str] = {}
    for m in mappings:
        orig = str(m.get("original") or "")
        if not orig:
            continue
        cands = m.get("candidates") or []
        chosen_code = selections.get(orig)
        chosen_pt = ""
        if chosen_code:
            for c in cands:
                if str(c.get("code")) == str(chosen_code):
                    chosen_pt = str(c.get("preferred_term") or "")
                    break
        elif cands:
            top = cands[0]
            if float(top.get("score") or 0) >= 0.9:
                chosen_code = str(top.get("code"))
                chosen_pt = str(top.get("preferred_term") or "")
        if chosen_code:
            code_map[orig] = chosen_code
            pt_map[orig] = chosen_pt

    s = df[col].astype("object")
    df[f"{col}{suffix_code}"] = s.map(lambda v: code_map.get(str(v).strip(), None) if v is not None else None)
    df[f"{col}{suffix_pt}"] = s.map(lambda v: pt_map.get(str(v).strip(), None) if v is not None else None)
    return df
