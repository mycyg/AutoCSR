"""Messy-tabular worker: csv / xlsx without CDISC dictionary.

Reads all sheets (xlsx) or the single csv; for each sheet emits one parquet +
one DataProfile. Adds an LLM-guessed semantic role for any column that the
local heuristic cannot resolve.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.schemas.ingest import IngestResult, DataProfile
from app.ingestion.workers._common import (
    profile_dataframe, raw_dir, write_parquet, suspect_role,
)


def _llm_role_guess(samples: dict[str, list[str]]) -> dict[str, str]:
    """Ask LLM to guess column semantic roles given column name + ≤3 sample values.

    Returns {col_name: role_string}. Best-effort — failures return {}.
    """
    try:
        from app.llm.ark_client import responses_json
        from app.llm.policy import for_role
    except ImportError:
        return {}
    if not samples:
        return {}
    schema = {
        "type": "object",
        "properties": {
            "roles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["column", "role"],
                },
            },
        },
        "required": ["roles"],
    }
    sys_msg = (
        "You are a CSR data-cleansing assistant. For each column, guess a short "
        "semantic role tag like: subject_id, age, sex, treatment, visit_date, "
        "ae_term, lab_value, weight, height, dose, score, response, comment, "
        "patient_name (PII), phone (PII), other. Output JSON only. NEVER pass "
        "values back, only role tags."
    )
    redacted = {
        k: [str(x)[:30] for x in vals[:3]]
        for k, vals in samples.items()
    }
    user_msg = "Columns and ≤3 sample values:\n" + json.dumps(redacted, ensure_ascii=False)
    policy = for_role("analyst")
    try:
        out = responses_json(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": user_msg}],
            schema, temperature=0.0,
            timeout=policy.timeout, max_tokens=1500,
        )
    except Exception:
        return {}
    result: dict[str, str] = {}
    for r in out.get("roles", []) or []:
        col = r.get("column")
        role = r.get("role")
        if isinstance(col, str) and isinstance(role, str) and role:
            result[col] = role
    return result


def _load_sheets(p: Path) -> dict[str, "Any"]:
    import pandas as pd
    if p.suffix.lower() == ".csv":
        return {"sheet1": pd.read_csv(p, dtype=str, encoding_errors="replace")}
    xls = pd.ExcelFile(p)
    return {name: xls.parse(name, dtype=str) for name in xls.sheet_names}


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    rdir = raw_dir(project_id, file_id)
    notes: list[str] = []
    try:
        sheets = _load_sheets(file_path)
    except Exception as e:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="messy_tabular",
            confidence=0.0, error=f"load failed: {e}",
        )

    artifacts: dict[str, str] = {}
    profiles: list[DataProfile] = []
    for sheet, df in sheets.items():
        if df.empty:
            notes.append(f"sheet {sheet} empty, skipped")
            continue
        # Local heuristic role
        cols = [str(c) for c in df.columns]
        unresolved = {
            c: df[c].dropna().astype(str).head(3).tolist()
            for c in cols if suspect_role(c) is None
        }
        llm_roles = _llm_role_guess(unresolved) if unresolved else {}
        prof = profile_dataframe(df, file_id=file_id, sheet=sheet)
        # Stamp LLM-guessed roles where heuristic was blank
        for cp in prof.columns:
            if not cp.suspected_role and cp.name in llm_roles:
                cp.suspected_role = llm_roles[cp.name]
                if cp.suspected_role in ("patient_name", "phone", "address",
                                         "email", "id_card", "mrn"):
                    cp.suspected_pii = True
        profiles.append(prof)
        out_pq = write_parquet(df, rdir / f"{sheet}.parquet")
        artifacts[f"parquet:{sheet}"] = out_pq

    (rdir / "meta.json").write_text(json.dumps({
        "ingest_type": "messy_tabular",
        "sheets": list(sheets.keys()),
        "source_filename": file_path.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts["meta"] = str(rdir / "meta.json")

    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="messy_tabular",
        confidence=0.8,
        artifacts=artifacts, profiles=profiles, notes=notes,
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
