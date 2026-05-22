"""Index principle PDFs (e.g. ICH E3.pdf, CDE guideline PDFs) into the corpus.

Placeholder for M2: if a PDF for a principle is found under data/principle_pdfs/<id>.pdf
it is chunked and stored as `principle` blocks under a special "_principles" project
so all real projects can grep against them. If no PDFs exist, prints a clear
message — the hardcoded YAML templates already contain everything needed for
outline generation.

Usage:
    python scripts/index_principles.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import data_dir
from app.principles import available_ids
from app.corpus.index import add_block, Block


def main() -> int:
    pdf_dir = data_dir() / "principle_pdfs"
    if not pdf_dir.exists() or not any(pdf_dir.glob("*.pdf")):
        print("[index_principles] no PDFs at", pdf_dir,
              "— principle YAML templates are self-sufficient; skipping.")
        return 0

    try:
        import pymupdf
    except ImportError:
        print("[index_principles] pymupdf not installed; cannot index PDFs.")
        return 1

    project_id = "_principles"
    pids = available_ids()
    print(f"[index_principles] indexing PDFs for principles: {pids}")

    indexed = 0
    for pid in pids:
        pdf = pdf_dir / f"{pid}.pdf"
        if not pdf.exists():
            continue
        doc = pymupdf.open(pdf)
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for para_idx, para in enumerate(paragraphs, start=1):
                add_block(project_id, Block(
                    id="",  # filled by add_block
                    project_id=project_id,
                    type="principle",
                    page=page_no,
                    col=1,
                    para=para_idx,
                    text=para[:4000],
                    meta={"principle_id": pid, "source_pdf": str(pdf.name)},
                ))
                indexed += 1
        doc.close()
    print(f"[index_principles] indexed {indexed} blocks across {len(pids)} principles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
