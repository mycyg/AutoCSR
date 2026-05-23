"""IngestType Router — mime + content + LLM tie-breaker.

Decision order:
  1. Extension/MIME prefilter
  2. Content sniffing (pandas head, pymupdf 2-page peek)
  3. CDISC dictionary column names → structured_data
  4. LLM (analyst tier) only if confidence < 0.7 after rules
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.ingest import IngestType


# Canonical SDTM / ADaM column names — presence of 2+ flips messy_tabular → structured.
CDISC_HINTS = {
    "USUBJID", "SUBJID", "STUDYID", "TRT01P", "TRT01A", "TRTSDT", "TRTEDT",
    "ARM", "ARMCD", "VISIT", "VISITNUM", "AGE", "AGEU", "SEX", "RACE", "ETHNIC",
    "AETERM", "AESOC", "AEDECOD", "AESEV", "AESER", "AESTDTC", "AEENDTC",
    "PARAM", "PARAMCD", "AVAL", "AVALC", "BASE", "CHG", "PCHG",
    "DISCRSN", "EOSSTT", "DTHFL", "SAFFL", "ITTFL", "EFFFL",
}


@dataclass
class RouteDecision:
    ingest_type: IngestType
    confidence: float
    reason: str


def _ext_lower(p: Path) -> str:
    return p.suffix.lower()


def _peek_csv_cols(p: Path, max_rows: int = 2) -> list[str]:
    try:
        import pandas as pd
        df = pd.read_csv(p, nrows=max_rows, dtype=str, encoding_errors="replace")
        return [str(c).upper().strip() for c in df.columns]
    except Exception:
        return []


def _peek_xlsx_cols(p: Path) -> list[str]:
    try:
        import pandas as pd
        df = pd.read_excel(p, sheet_name=0, nrows=2, dtype=str)
        return [str(c).upper().strip() for c in df.columns]
    except Exception:
        return []


def _peek_pdf(p: Path) -> dict[str, Any]:
    """Return {has_text_layer, n_form_fields, sample_text} from first 2 pages."""
    out: dict[str, Any] = {"has_text_layer": False, "n_form_fields": 0, "sample_text": ""}
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return out
    try:
        doc = pymupdf.open(p)
    except Exception:
        return out
    try:
        texts: list[str] = []
        n_fields = 0
        for page in doc[:2]:
            t = page.get_text("text") or ""
            texts.append(t)
            try:
                widgets = list(page.widgets() or [])
                n_fields += len(widgets)
            except Exception:
                pass
        joined = "\n".join(texts)
        out["has_text_layer"] = len(joined.strip()) >= 40
        out["n_form_fields"] = n_fields
        out["sample_text"] = joined[:1200]
    finally:
        doc.close()
    return out


def _llm_tiebreak(file_name: str, sample_text: str) -> tuple[IngestType, float] | None:
    """Ask analyst LLM to pick among the 6 types. Best-effort; failures return None."""
    try:
        from app.llm.ark_client import responses_json, ArkError
        from app.llm.policy import for_role
    except ImportError:
        return None
    schema = {
        "type": "object",
        "properties": {
            "ingest_type": {"type": "string", "enum": [
                "structured_data", "messy_tabular", "pdf_form", "scan_crf",
                "handwriting", "literature_doc",
            ]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["ingest_type", "confidence"],
    }
    try:
        from app.i18n.loader import load_prompt
        sys_msg = load_prompt("router", "en")
    except Exception:
        sys_msg = (
            "You classify clinical-trial artefacts for an ICH E3 CSR pipeline. "
            "Pick ONE of: structured_data, messy_tabular, pdf_form, scan_crf, "
            "handwriting, literature_doc. Output JSON only."
        )
    user_msg = (
        f"filename: {file_name}\n"
        f"first 1.2k chars:\n---\n{sample_text}\n---\n"
        "Decide the most likely ingest type."
    )
    policy = for_role("analyst")
    try:
        out = responses_json(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": user_msg}],
            schema, temperature=0.0,
            timeout=policy.timeout, max_tokens=400,
        )
    except (ArkError, Exception):
        return None
    t = out.get("ingest_type")
    c = out.get("confidence")
    if t in {"structured_data", "messy_tabular", "pdf_form", "scan_crf",
             "handwriting", "literature_doc"} and isinstance(c, (int, float)):
        return t, float(c)  # type: ignore[return-value]
    return None


async def route(file_path: str | Path) -> RouteDecision:
    p = Path(file_path)
    if not p.exists():
        return RouteDecision("literature_doc", 0.0, "file not found")
    ext = _ext_lower(p)
    mime, _ = mimetypes.guess_type(p.name)

    # 1. SAS — always structured
    if ext in {".xpt", ".sas7bdat"}:
        return RouteDecision("structured_data", 0.99, f"SAS dataset {ext}")

    # 2. CSV/XLSX → look at columns for CDISC dictionary
    if ext == ".csv":
        cols = await asyncio.to_thread(_peek_csv_cols, p)
        hits = sum(1 for c in cols if c in CDISC_HINTS)
        if hits >= 2:
            return RouteDecision("structured_data", 0.92, f"{hits} CDISC columns")
        if cols:
            return RouteDecision("messy_tabular", 0.75, "tabular csv, no CDISC dict")
        return RouteDecision("messy_tabular", 0.4, "csv unreadable header")

    if ext in {".xlsx", ".xls"}:
        cols = await asyncio.to_thread(_peek_xlsx_cols, p)
        hits = sum(1 for c in cols if c in CDISC_HINTS)
        if hits >= 2:
            return RouteDecision("structured_data", 0.9, f"{hits} CDISC columns")
        return RouteDecision("messy_tabular", 0.7, "xlsx, no CDISC dict")

    # 3. Word docs — literature
    if ext in {".doc", ".docx"}:
        return RouteDecision("literature_doc", 0.9, "word document")

    # 4. Plain text / markdown — literature
    if ext in {".txt", ".md"}:
        return RouteDecision("literature_doc", 0.85, "plain text / markdown")

    # 5. PDF — inspect text layer
    if ext == ".pdf":
        info = await asyncio.to_thread(_peek_pdf, p)
        if info["n_form_fields"] >= 3:
            return RouteDecision("pdf_form", 0.85, f"{info['n_form_fields']} form fields")
        if not info["has_text_layer"]:
            return RouteDecision("scan_crf", 0.7, "no text layer")
        sample = info["sample_text"]
        # Heuristic: form-like (many short lines + colon) vs prose
        if sample:
            lines = [l for l in sample.splitlines() if l.strip()]
            short_colon = sum(1 for l in lines if len(l) < 80 and ":" in l)
            if lines and short_colon / max(1, len(lines)) > 0.4:
                return RouteDecision("pdf_form", 0.7, "form-like text layout")
            return RouteDecision("literature_doc", 0.8, "prose pdf")
        # Fall through to LLM
        guess = _llm_tiebreak(p.name, sample)
        if guess:
            return RouteDecision(guess[0], guess[1], "llm tiebreak (pdf empty layer)")
        return RouteDecision("literature_doc", 0.5, "pdf default")

    # 6. Images
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        return RouteDecision("scan_crf", 0.6, "image — treat as scan")

    # Unknown — try LLM
    guess = _llm_tiebreak(p.name, "")
    if guess:
        return RouteDecision(guess[0], guess[1], "llm tiebreak (unknown ext)")
    return RouteDecision("literature_doc", 0.3, "unknown extension default")
