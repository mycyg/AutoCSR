"""Scan CRF worker (M2.5): image-PDF → OCR/visual structure with confidences."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.schemas.ingest import IngestResult
from app.ingestion.workers._common import raw_dir


def _ocr_page(page) -> tuple[str, float]:
    """Best-effort OCR. pytesseract is optional; without it we stub."""
    try:
        import pytesseract  # type: ignore
        import pymupdf  # type: ignore  # noqa: F401
    except ImportError:
        return "", 0.0
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return "", 0.0
    try:
        pix = page.get_pixmap(dpi=200)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words = [w for w in data.get("text", []) if w and w.strip()]
        confs = [int(c) for c in data.get("conf", []) if c and str(c).strip("-").isdigit()]
        text = " ".join(words)
        avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return text, avg_conf
    except Exception:
        return "", 0.0


def _build(file_path: Path, project_id: str, file_id: str) -> IngestResult:
    rdir = raw_dir(project_id, file_id)
    try:
        import pymupdf  # type: ignore
    except ImportError:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="scan_crf",
            confidence=0.0, error="pymupdf not installed",
        )
    cells: list[dict] = []
    needs_review = False
    try:
        if file_path.suffix.lower() == ".pdf":
            doc = pymupdf.open(file_path)
            try:
                for i, page in enumerate(doc, start=1):
                    text, conf = _ocr_page(page)
                    if not text:
                        needs_review = True
                        cells.append({
                            "page": i, "text": "", "confidence": 0.0,
                            "needs_review": True, "reason": "OCR unavailable or empty",
                        })
                    else:
                        cells.append({"page": i, "text": text[:4000], "confidence": conf,
                                      "needs_review": conf < 0.6})
                        if conf < 0.6:
                            needs_review = True
            finally:
                doc.close()
        else:
            # raw image — stub one cell
            needs_review = True
            cells.append({
                "page": 1, "text": "", "confidence": 0.0,
                "needs_review": True, "reason": "image OCR stub",
            })
    except Exception as e:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type="scan_crf",
            confidence=0.0, error=f"scan failure: {e}",
        )

    (rdir / "ocr.json").write_text(json.dumps({
        "ingest_type": "scan_crf", "cells": cells,
        "source_filename": file_path.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    overall = sum(c.get("confidence", 0.0) for c in cells) / max(1, len(cells))
    return IngestResult(
        file_id=file_id, project_id=project_id, ingest_type="scan_crf",
        confidence=overall,
        artifacts={"ocr_json": str(rdir / "ocr.json")},
        needs_review=needs_review or overall < 0.6,
        notes=[f"{len(cells)} page(s) OCR'd", f"avg_conf={overall:.2f}"],
    )


async def run(file_path, project_id: str, file_id: str) -> IngestResult:
    return await asyncio.to_thread(_build, Path(file_path), project_id, file_id)
