"""Proposes cleansing rules from a DataProfile + IngestResult.

Two sources:
  1. Deterministic rules (always run first — fast, no LLM cost)
     * hash_pii for every column flagged suspected_pii
     * cast_dtype when numeric content but dtype=='object'
     * impute_missing when null_rate > 5%
     * outlier_flag when numeric_outlier_count > 0
  2. LLM proposer (analyst tier) for the longer tail of suggestions
     * Sends column-level profile + ≤5 sample values (PII columns masked)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.schemas.cleansing import CleansingProposal
from app.schemas.ingest import DataProfile, IngestResult


def _redacted_samples(profile: DataProfile) -> list[dict[str, Any]]:
    """Build LLM-safe column summaries with PII values masked."""
    out: list[dict[str, Any]] = []
    strict = settings().get("pipeline", {}).get("llm_data_redaction", "strict") == "strict"
    for c in profile.columns:
        item: dict[str, Any] = {
            "name": c.name, "dtype": c.dtype, "null_rate": round(c.null_rate, 3),
            "n_unique": c.n_unique, "role": c.suspected_role,
            "pii": c.suspected_pii,
        }
        if c.suspected_pii and strict:
            item["sample_values"] = ["<redacted>"] * min(3, len(c.sample_values))
        else:
            item["sample_values"] = c.sample_values[:5]
        if c.numeric_min is not None:
            item["numeric"] = {"min": c.numeric_min, "max": c.numeric_max,
                               "mean": c.numeric_mean,
                               "outliers": c.numeric_outlier_count}
        if c.top_freq:
            item["top_freq"] = c.top_freq[:5]
        out.append(item)
    return out


def _deterministic(profile: DataProfile, ingest: IngestResult) -> list[CleansingProposal]:
    out: list[CleansingProposal] = []
    n_rows = profile.n_rows

    def mk(p_type: str, cols: list[str], params: dict[str, Any], rationale: str,
           *, confidence: float, impact: int, mandatory: bool = False) -> CleansingProposal:
        return CleansingProposal(
            id=uuid.uuid4().hex[:12],
            project_id=ingest.project_id, file_id=ingest.file_id,
            sheet=profile.sheet, type=p_type,  # type: ignore[arg-type]
            target_columns=cols, parameters=params,
            rationale=rationale, confidence=confidence,
            impact_rows=impact, mandatory=mandatory,
            created_at=datetime.now(timezone.utc),
        )

    for c in profile.columns:
        if c.suspected_pii:
            out.append(mk(
                "hash_pii", [c.name],
                {"algo": "sha256", "salt_env": "AUTOCSR_PII_SALT"},
                f"列 `{c.name}` 疑似 PII（role={c.suspected_role}），按策略默认接受。",
                confidence=1.0, impact=n_rows, mandatory=True,
            ))
        # Numeric content stored as object
        if c.dtype == "object" and c.numeric_min is not None and c.numeric_max is not None:
            ratio_numeric = 1.0 - c.null_rate
            if ratio_numeric > 0.5 and c.suspected_role not in ("subject_id",):
                out.append(mk(
                    "cast_dtype", [c.name],
                    {"to": "float", "errors": "coerce"},
                    f"列 `{c.name}` 看起来主要是数字但 dtype=object，可解析为 float。",
                    confidence=0.85,
                    impact=int(n_rows * ratio_numeric),
                ))
        if c.null_rate > 0.05 and c.null_rate < 0.6:
            strategy = "median" if c.numeric_min is not None else "mode"
            out.append(mk(
                "impute_missing", [c.name],
                {"strategy": strategy},
                f"列 `{c.name}` 缺失率 {c.null_rate:.1%}，建议用 {strategy} 填补。",
                confidence=0.7,
                impact=int(n_rows * c.null_rate),
            ))
        if c.numeric_outlier_count and c.numeric_outlier_count > 0:
            out.append(mk(
                "outlier_flag", [c.name],
                {"method": "iqr", "k": 1.5, "new_column": f"{c.name}__outlier"},
                f"列 `{c.name}` IQR 检测到 {c.numeric_outlier_count} 个离群点，建议标记不剔除。",
                confidence=0.65,
                impact=c.numeric_outlier_count,
            ))
    return out


def _llm_proposals(profile: DataProfile, ingest: IngestResult) -> list[CleansingProposal]:
    try:
        from app.llm.ark_client import responses_json
        from app.llm.policy import for_role
    except ImportError:
        return []
    schema = {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": [
                            "rename_column", "cast_dtype", "unit_convert",
                            "normalize_value", "split_column", "merge_columns",
                            "derive_column",
                        ]},
                        "target_columns": {"type": "array", "items": {"type": "string"}},
                        "parameters": {"type": "object"},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["type", "target_columns", "rationale"],
                },
            },
        },
        "required": ["proposals"],
    }
    try:
        from app.i18n.loader import load_prompt
        sys_msg = load_prompt("proposer", "en")
    except Exception:
        sys_msg = (
            "You propose cleansing rules for clinical-trial tabular data destined "
            "for an ICH E3 CSR. Stick to these proposal types: rename_column, "
            "cast_dtype, unit_convert, normalize_value, split_column, merge_columns, "
            "derive_column. Be conservative — never propose deletion. Use Chinese "
            "rationale for Chinese column names, English for English column names. "
            "Output JSON only."
        )
    profile_payload = {
        "sheet": profile.sheet,
        "n_rows": profile.n_rows, "n_cols": profile.n_cols,
        "encoding_issues": profile.encoding_issues,
        "columns": _redacted_samples(profile),
    }
    user_msg = (
        f"Ingest type: {ingest.ingest_type}\n"
        f"Profile (PII masked):\n{json.dumps(profile_payload, ensure_ascii=False)}\n\n"
        "Propose up to 8 cleansing rules tailored to these columns."
    )
    policy = for_role("analyst")
    try:
        out = responses_json(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": user_msg}],
            schema, temperature=0.1,
            timeout=policy.timeout, max_tokens=3000,
        )
    except Exception:
        return []
    items: list[CleansingProposal] = []
    for p in out.get("proposals", []) or []:
        try:
            items.append(CleansingProposal(
                id=uuid.uuid4().hex[:12],
                project_id=ingest.project_id, file_id=ingest.file_id,
                sheet=profile.sheet,
                type=p["type"], target_columns=p["target_columns"],
                parameters=p.get("parameters") or {},
                rationale=p.get("rationale", ""),
                confidence=float(p.get("confidence") or 0.6),
                impact_rows=profile.n_rows,
                created_at=datetime.now(timezone.utc),
            ))
        except Exception:
            continue
    return items


async def propose(profile: DataProfile, ingest: IngestResult,
                  *, use_llm: bool = True) -> list[CleansingProposal]:
    import asyncio
    out = _deterministic(profile, ingest)
    # Dictionary-driven map_to_cdisc proposals (no LLM, fast)
    try:
        from app.cleansing.proposals.map_to_cdisc import build_proposals as _mtc
        seen_mtc = {(p.type, tuple(p.target_columns)) for p in out}
        for p in _mtc(profile, ingest):
            if (p.type, tuple(p.target_columns)) not in seen_mtc:
                out.append(p)
    except Exception:
        pass
    if use_llm:
        llm_items = await asyncio.to_thread(_llm_proposals, profile, ingest)
        # Dedup: skip LLM proposals that collide with deterministic on same (type, columns)
        seen = {(p.type, tuple(p.target_columns)) for p in out}
        for p in llm_items:
            if (p.type, tuple(p.target_columns)) not in seen:
                out.append(p)
    return out
