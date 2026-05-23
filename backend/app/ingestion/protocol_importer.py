"""M21 — protocol PDF → structured trial-design metadata.

The 8-field extraction:
    study_id, phase, indication, treatment, endpoints, population,
    design_type, sample_size

The LLM call uses the project's existing analyst_llm path; when the LLM
is unreachable / disabled (CSR_LLM_MOCK=1, env or settings.llm.api_key
empty) we fall back to regex-based heuristics so the e2e suite stays
deterministic.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("autocsr.ingestion.protocol")


class ProtocolMetadata(BaseModel):
    study_id: str = ""
    phase: str = ""
    indication: str = ""
    treatment: str = ""
    endpoints: list[str] = Field(default_factory=list)
    population: str = ""
    design_type: str = ""
    sample_size: int | None = None
    extra_notes: str = ""


class ImportResult(BaseModel):
    project_id: str
    source_filename: str
    metadata: ProtocolMetadata
    corpus_block_id: str | None = None
    used_mock: bool = False
    raw_excerpt: str = ""


SYSTEM_PROMPT = """You are extracting structured metadata from a clinical
trial protocol. Read the excerpt and return a single JSON object with the
keys: study_id, phase, indication, treatment, endpoints (array),
population, design_type, sample_size (integer or null), extra_notes.
If a field is unclear, use "" (or [] / null). Do not invent values."""


def _extract_text(pdf_path: Path, max_pages: int = 30) -> str:
    try:
        import fitz  # pymupdf
    except Exception:
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        parts: list[str] = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            parts.append(page.get_text("text") or "")
        doc.close()
        return "\n".join(parts)
    except Exception as e:
        logger.warning("protocol_pdf_text_extract_failed: %s", e)
        return ""


def _heuristic_extract(text: str) -> ProtocolMetadata:
    """Cheap regex fallback so mock mode + missing-LLM both produce a
    populated metadata object."""
    txt = text or ""
    lower = txt.lower()

    def grep(pattern: str, group: int = 1) -> str:
        m = re.search(pattern, txt, flags=re.IGNORECASE | re.MULTILINE)
        if not m:
            return ""
        try:
            return (m.group(group) or "").strip()
        except IndexError:
            return ""

    study_id = grep(r"(?:protocol|study)\s*(?:no\.?|number|id)[:\s]+([A-Z0-9\-_]{3,30})")
    if not study_id:
        study_id = grep(r"\b([A-Z]{2,}[-_]?\d{3,6})\b")
    phase = ""
    m = re.search(r"phase\s*(I{1,3}|IV|1|2|3|4|[IVab]+)", txt, flags=re.IGNORECASE)
    if m:
        phase = "Phase " + m.group(1).upper().replace("IV", "4").replace("III", "3") \
            .replace("II", "2").replace("I", "1")
    indication = grep(r"indication[:\s]+([^\n\r]{3,120})")
    treatment = grep(r"(?:investigational|treatment|drug)[:\s]+([^\n\r]{3,120})")
    population = grep(r"(?:target population|population)[:\s]+([^\n\r]{3,120})")
    design_type = ""
    for keyword in ("randomized", "double-blind", "open-label", "single-arm",
                    "crossover", "parallel", "placebo-controlled"):
        if keyword in lower:
            design_type = (design_type + ", " + keyword) if design_type else keyword
    sample_size: int | None = None
    m = re.search(r"sample\s*size[:\s]+(\d{2,5})", txt, flags=re.IGNORECASE)
    if m:
        try:
            sample_size = int(m.group(1))
        except ValueError:
            sample_size = None
    endpoints: list[str] = []
    for label in ("primary endpoint", "secondary endpoint", "key secondary endpoint"):
        for m in re.finditer(rf"{label}[:\s]+([^\n\r]+)", txt, flags=re.IGNORECASE):
            ep = m.group(1).strip()
            if ep and ep not in endpoints:
                endpoints.append(ep)
    return ProtocolMetadata(
        study_id=study_id, phase=phase, indication=indication,
        treatment=treatment, endpoints=endpoints, population=population,
        design_type=design_type, sample_size=sample_size,
    )


def _llm_extract(text: str) -> ProtocolMetadata | None:
    """Best-effort LLM extraction. Returns None on any failure so we can
    fall back to the heuristic path."""
    try:
        from app.llm.ark_client import call_llm  # type: ignore
    except Exception:
        try:
            from app.llm.client import call_llm  # type: ignore
        except Exception:
            return None
    excerpt = text[:8000]
    user_prompt = (
        "Protocol excerpt:\n```\n" + excerpt + "\n```\n\n"
        "Respond with ONLY the JSON object."
    )
    try:
        resp = call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.get("text") or resp.get("content") or ""
        if not raw:
            return None
        obj = json.loads(raw)
        return ProtocolMetadata(**obj)
    except Exception as e:
        logger.warning("protocol_llm_extract_failed: %s", e)
        return None


def _is_mock() -> bool:
    if os.environ.get("CSR_LLM_MOCK"):
        return True
    if os.environ.get("CSR_PROTOCOL_MOCK"):
        return True
    try:
        from app.config import settings
        if not (settings().get("llm") or {}).get("api_key"):
            return True
    except Exception:
        pass
    return False


def import_protocol(project_id: str, pdf_path: str | Path,
                     source_filename: str | None = None) -> ImportResult:
    p = Path(pdf_path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    text = _extract_text(p)
    meta: ProtocolMetadata | None = None
    used_mock = _is_mock()
    if not used_mock:
        meta = _llm_extract(text)
        if meta is None:
            used_mock = True
    if meta is None:
        meta = _heuristic_extract(text)
    # Persist into project config notes + corpus
    block_id: str | None = None
    try:
        from app.config.project_config import get_config, save_config
        cfg = get_config(project_id)
        notes = (cfg.model_dump().get("notes") if hasattr(cfg, "notes") else None) or ""
        block_text = (
            "[Protocol import] "
            f"study={meta.study_id}; phase={meta.phase}; indication={meta.indication}; "
            f"treatment={meta.treatment}; design={meta.design_type}; n={meta.sample_size}; "
            f"endpoints={', '.join(meta.endpoints)}"
        )
        # ProjectConfig has no 'notes' field in current schema; we store
        # under data/projects/<pid>/notes/protocol.json instead.
        from app.config import data_dir
        notes_dir = data_dir() / "projects" / project_id / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / "protocol.json").write_text(
            json.dumps({
                "metadata": json.loads(meta.model_dump_json()),
                "source": source_filename or p.name,
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "used_mock": used_mock,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("protocol_notes_save_failed: %s", e)
    # Mirror to corpus as a 'note' block so writer agents can grep it.
    try:
        from app.corpus.index import Block, add_block
        block = Block(
            id="proto_" + (meta.study_id.replace(" ", "_")[:20] or "import"),
            project_id=project_id,
            type="note",
            page=1, col=1, para=1,
            text=block_text,
            meta={
                "kind": "protocol_metadata",
                "source": source_filename or p.name,
                "study_id": meta.study_id,
                "phase": meta.phase,
                "indication": meta.indication,
            },
        )
        block_id = add_block(project_id, block)
    except Exception as e:
        logger.warning("protocol_corpus_save_failed: %s", e)
    return ImportResult(
        project_id=project_id,
        source_filename=source_filename or p.name,
        metadata=meta,
        corpus_block_id=block_id,
        used_mock=used_mock,
        raw_excerpt=text[:500],
    )
