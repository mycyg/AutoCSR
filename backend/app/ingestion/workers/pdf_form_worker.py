"""PDF-form worker: text-PDF with fields → structured rows + form-text corpus blocks."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.corpus.index import Block, add_block
from app.schemas.ingest import IngestResult
from app.ingestion.workers._common import raw_dir


def _extract(file_path: Path) -> tuple[list[dict], list[str]]:
    """Return (form_fields, page_texts)."""
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return [], []
    doc = pymupdf.open(file_path)
    fields: list[dict] = []
    page_texts: list[str] = []
    try:
        for i, page in enumerate(doc, start=1):
            page_texts.append(page.get_text("text") or "")
            try:
                widgets = list(page.widgets() or [])
            except Exception:
                widgets = []
            for w in widgets:
                fields.append({
                    "page": i,
                    "field_name": getattr(w, "field_name", None),
                    "field_value": getattr(w, "field_value", None),
                    "field_type": getattr(w, "field_type_string", None),
                })
    finally:
        doc.close()
    return fields, page_texts


def _llm_structure(page_texts: list[str]) -> dict | None:
    """Ask LLM for a structured JSON projection of the form text."""
    try:
        from app.llm.ark_client import responses_json
        from app.llm.policy import for_role
    except ImportError:
        return None
    if not page_texts:
        return None
    schema = {
        "type": "object",
        "properties": {
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                        "page": {"type": "integer"},
                    },
                    "required": ["label", "value"],
                },
            },
        },
        "required": ["fields"],
    }
    joined = "\n\n=== PAGE BREAK ===\n\n".join(page_texts[:5])
    sys_msg = (
        "Extract label/value pairs from a CRF / form PDF. Only return fields "
        "that have a clear value (skip blanks). Output JSON only."
    )
    user_msg = "Form text:\n" + joined[:8000]
    policy = for_role("analyst")
    try:
        return responses_json(
            [{"role": "system", "content": sys_msg},
             {"role": "user", "content": user_msg}],
            schema, temperature=0.0,
            timeout=policy.timeout, max_tokens=4000,
        )
    except Exception:
        return None


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    rdir = raw_dir(project_id, file_id)
    fields, page_texts = _extract(file_path)
    structured = _llm_structure(page_texts) if page_texts else None
    block_ids: list[str] = []
    for i, t in enumerate(page_texts, start=1):
        snippet = (t or "").strip()
        if len(snippet) < 20:
            continue
        bid = add_block(project_id, Block(
            id="", project_id=project_id, type="literature",
            page=i, col=1, para=1, text=snippet,
            meta={"source_file_id": file_id, "kind": "pdf_form"},
        ))
        block_ids.append(bid)
    (rdir / "fields.json").write_text(json.dumps({
        "widget_fields": fields,
        "llm_structured": structured,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    notes = [f"extracted {len(fields)} widget fields", f"{len(page_texts)} pages of text"]
    if structured and structured.get("fields"):
        notes.append(f"llm parsed {len(structured['fields'])} label/value pairs")
    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="pdf_form",
        confidence=0.85 if fields or structured else 0.5,
        artifacts={"fields_json": str(rdir / "fields.json")},
        corpus_block_ids=block_ids, notes=notes,
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
