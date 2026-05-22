"""Handwriting worker (M2.5): printed parts only, handwritten regions flagged for user.

Rule: never let the LLM hallucinate handwritten content. Each handwritten region
emits {value: null, needs_user_input: true, bbox: [...]}.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.schemas.ingest import IngestResult
from app.ingestion.workers._common import raw_dir


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    rdir = raw_dir(project_id, file_id)
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="handwriting",
            confidence=0.0, error="pymupdf not installed",
        )

    printed: list[dict] = []
    handwritten: list[dict] = []

    try:
        if file_path.suffix.lower() == ".pdf":
            doc = pymupdf.open(file_path)
            try:
                for i, page in enumerate(doc, start=1):
                    text = page.get_text("text") or ""
                    if text.strip():
                        printed.append({"page": i, "text": text[:4000]})
                    # Heuristic: drawings / annotations on the page often indicate
                    # handwriting overlays. Mark whole-page as needs-user-input.
                    try:
                        draws = page.get_drawings() or []
                    except Exception:
                        draws = []
                    if draws or not text.strip():
                        handwritten.append({
                            "page": i,
                            "bbox": [0, 0, page.rect.width, page.rect.height],
                            "value": None,
                            "needs_user_input": True,
                            "reason": "handwritten region — operator must transcribe",
                        })
            finally:
                doc.close()
        else:
            # image: always flag whole frame as needing user input
            handwritten.append({
                "page": 1, "bbox": None, "value": None,
                "needs_user_input": True, "reason": "image — handwriting suspected",
            })
    except Exception as e:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="handwriting",
            confidence=0.0, error=f"handwriting parse failure: {e}",
        )

    (rdir / "handwriting.json").write_text(json.dumps({
        "ingest_type": "handwriting",
        "printed": printed, "handwritten": handwritten,
        "source_filename": file_path.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="handwriting",
        confidence=0.7 if printed else 0.4,
        artifacts={"handwriting_json": str(rdir / "handwriting.json")},
        needs_review=bool(handwritten),
        notes=[f"{len(printed)} printed regions", f"{len(handwritten)} handwritten flagged"],
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
