"""Per-type ingestion workers.

Every worker:
    async def run(file_path: Path, project_id: str, file_id: str) -> IngestResult
"""
from app.ingestion.workers import (
    structured_worker, excel_worker, pdf_form_worker,
    lit_worker, scan_worker, handwriting_worker,
)
from app.schemas.ingest import IngestType, IngestResult


WORKERS = {
    "structured_data": structured_worker,
    "messy_tabular": excel_worker,
    "pdf_form": pdf_form_worker,
    "literature_doc": lit_worker,
    "scan_crf": scan_worker,
    "handwriting": handwriting_worker,
}


async def dispatch(ingest_type: IngestType, file_path, project_id: str, file_id: str) -> IngestResult:
    worker = WORKERS.get(ingest_type)
    if worker is None:
        return IngestResult(
            file_id=file_id, project_id=project_id, ingest_type=ingest_type,
            confidence=0.0, error=f"no worker for {ingest_type}",
        )
    return await worker.run(file_path, project_id, file_id)


__all__ = ["WORKERS", "dispatch"]
