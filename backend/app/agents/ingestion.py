"""BaseAgent wrappers around the existing 6 ingest workers.

Each ingest worker exposes ``async def run(file_path, project_id, file_id)``;
we wrap them here so the orchestrator can also drive them through the
uniform AgentInput/AgentOutput interface and pick up structured logging.
"""
from __future__ import annotations

from app.agents.base import AgentError, BaseAgent
from app.ingestion.workers import (
    excel_worker, handwriting_worker, lit_worker,
    pdf_form_worker, scan_worker, structured_worker,
)
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.ingest import IngestType


_TYPE_TO_MODULE = {
    "structured_data": structured_worker,
    "messy_tabular": excel_worker,
    "pdf_form": pdf_form_worker,
    "literature_doc": lit_worker,
    "scan_crf": scan_worker,
    "handwriting": handwriting_worker,
}


class IngestWorkerAgent(BaseAgent):
    """Single-worker agent.

    ``input.payload`` must carry: ``ingest_type``, ``file_path``, ``file_id``.
    The result is the ``IngestResult`` produced by the underlying worker.
    """

    name = "IngestWorker"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        ingest_type: IngestType = payload.get("ingest_type")  # type: ignore[assignment]
        file_path = payload.get("file_path")
        file_id = payload.get("file_id")
        if not (ingest_type and file_path and file_id):
            raise AgentError("missing ingest_type / file_path / file_id",
                              retryable=False)
        mod = _TYPE_TO_MODULE.get(ingest_type)
        if mod is None:
            raise AgentError(f"no worker for ingest_type={ingest_type!r}",
                              retryable=False)
        try:
            result = await mod.run(file_path, agent_input.project_id, file_id)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"worker {ingest_type} failed: {e}", cause=e)
        warnings: list[str] = []
        ok = True
        if result.error:
            warnings.append(f"worker_error:{result.error}")
            ok = False
        return AgentOutput(
            ok=ok,
            result=result.model_dump(),
            warnings=warnings,
            meta={"ingest_type": ingest_type, "file_id": file_id},
        )
