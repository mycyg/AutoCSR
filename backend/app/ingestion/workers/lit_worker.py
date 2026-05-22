"""Literature worker: PDF / DOCX / plain-text → markdown blocks in corpus."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.corpus.index import Block, add_block
from app.schemas.ingest import IngestResult
from app.ingestion.workers._common import raw_dir


def _pdf_blocks(file_path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return out
    doc = pymupdf.open(file_path)
    try:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for para_idx, para in enumerate(paragraphs, start=1):
                if len(para) < 25:
                    continue
                out.append({"page": i, "para": para_idx, "text": para[:4000]})
    finally:
        doc.close()
    return out


def _docx_blocks(file_path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        from docx import Document  # type: ignore
    except ImportError:
        return out
    try:
        doc = Document(str(file_path))
    except Exception:
        return out
    para_idx = 0
    for para in doc.paragraphs:
        txt = (para.text or "").strip()
        if len(txt) < 25:
            continue
        para_idx += 1
        out.append({"page": 1, "para": para_idx, "text": txt[:4000]})
    return out


def _txt_blocks(file_path: Path) -> list[dict]:
    try:
        raw = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
    return [{"page": 1, "para": i, "text": p[:4000]}
            for i, p in enumerate(paragraphs, start=1) if len(p) >= 10]


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        blocks = _pdf_blocks(file_path)
    elif ext in {".docx", ".doc"}:
        blocks = _docx_blocks(file_path)
    else:
        blocks = _txt_blocks(file_path)

    rdir = raw_dir(project_id, file_id)
    block_ids: list[str] = []
    for b in blocks:
        bid = add_block(project_id, Block(
            id="", project_id=project_id, type="literature",
            page=b["page"], col=1, para=b["para"], text=b["text"],
            meta={"source_file_id": file_id, "source_filename": file_path.name},
        ))
        block_ids.append(bid)

    (rdir / "meta.json").write_text(json.dumps({
        "ingest_type": "literature_doc",
        "source_filename": file_path.name,
        "n_blocks": len(block_ids),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="literature_doc",
        confidence=0.9 if block_ids else 0.4,
        artifacts={"meta": str(rdir / "meta.json")},
        corpus_block_ids=block_ids,
        notes=[f"created {len(block_ids)} literature blocks"],
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
