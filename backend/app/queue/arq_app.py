"""arq Worker definition for AutoCSR (M19).

When ``queue.backend: arq`` is selected (or the matching env var
``AUTOCSR_QUEUE_BACKEND=arq``), long-running jobs are submitted to a
Redis-backed ``arq`` queue. The Worker process imported here picks
them up and executes the same handler functions the inmemory backend
would have run.

Operational notes
-----------------
* The Worker is started via ``scripts/run_arq_worker.py`` (sidecar
  container in docker-compose). Multiple workers are safe — arq uses
  Redis SETNX for job-level fairness.
* Each handler takes ``ctx`` (the arq context) plus the same payload
  the route would have passed to :func:`app.queue.runtime.enqueue`.
* We re-register every handler in :func:`_collect_handlers` so the
  Worker startup doesn't depend on the FastAPI app boot path having
  run first.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings

logger = logging.getLogger("autocsr.queue.arq")


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _redis_url() -> str:
    env = os.environ.get("AUTOCSR_REDIS_URL")
    if env:
        return env
    seg = settings().get("queue") or {}
    return str(seg.get("redis_url") or "redis://127.0.0.1:6379/0")


def _redis_settings():  # pragma: no cover - defers to arq
    from arq.connections import RedisSettings  # type: ignore
    return RedisSettings.from_dsn(_redis_url())


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------
#
# Each handler is a coroutine ``async def fn(ctx, **payload) -> dict``.
# They re-use the production code paths so behaviour stays identical to
# the inmemory queue.

async def ingest_all_task(ctx: dict[str, Any], *, project_id: str,
                          file_ids: list[str] | None = None) -> dict[str, Any]:
    """Run the M2 ingest router across all uploaded files of a project."""
    from app.ingestion.router import run_router  # type: ignore[attr-defined]
    res = await run_router(project_id, file_ids=file_ids)
    return {"ok": True, "n_files": len(getattr(res, "files", []) or [])}


async def cleansing_apply_task(ctx: dict[str, Any], *, project_id: str,
                               proposal_ids: list[str] | None = None,
                               ) -> dict[str, Any]:
    from app.cleansing.workbench import apply_all  # type: ignore[attr-defined]
    res = await apply_all(project_id, proposal_ids=proposal_ids)
    return {"ok": True, "applied": res}


async def report_generate_task(ctx: dict[str, Any], *, project_id: str,
                               harmonize: bool = True,
                               leaf_limit: int | None = None,
                               task_id: str | None = None) -> dict[str, Any]:
    from app.report.orchestrator import write_all
    out = await write_all(project_id, harmonize=harmonize,
                          leaf_limit=leaf_limit, task_id=task_id)
    return {"ok": True, "report": getattr(out, "project_id", project_id)}


async def multi_review_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.agents.reviewers.multi import run_multi_review
    res = await run_multi_review(project_id)
    return res.model_dump()


# ---- export tasks (M19) ----------------------------------------------------

async def export_pdf_task(ctx: dict[str, Any], *, project_id: str,
                          template_config: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.export.pdf_builder import build_pdf
    res = build_pdf(project_id, template_config=template_config)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes}


async def export_html_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.export.html_builder import build_html
    res = build_html(project_id)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes}


async def export_pptx_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.export.pptx_builder import build_pptx
    res = build_pptx(project_id)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes,
            "n_slides": res.n_slides}


async def export_md_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.export.markdown_bundle import build_markdown_bundle
    res = build_markdown_bundle(project_id)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes,
            "n_files": res.n_files}


async def export_ectd_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.export.ectd_packager import build_ectd
    res = build_ectd(project_id)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes}


async def tlf_export_task(ctx: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    from app.analysis.tlf_export import build_tlf_zip  # type: ignore[attr-defined]
    res = build_tlf_zip(project_id)
    return {"ok": True, "filename": res.filename, "size_bytes": res.size_bytes}


# ---------------------------------------------------------------------------
# WorkerSettings (arq entrypoint)
# ---------------------------------------------------------------------------

def _collect_handlers() -> list:
    return [
        ingest_all_task,
        cleansing_apply_task,
        report_generate_task,
        multi_review_task,
        export_pdf_task,
        export_html_task,
        export_pptx_task,
        export_md_task,
        export_ectd_task,
        tlf_export_task,
    ]


async def _on_startup(ctx: dict[str, Any]) -> None:  # pragma: no cover
    logger.info("autocsr arq worker startup; redis=%s", _redis_url())


async def _on_shutdown(ctx: dict[str, Any]) -> None:  # pragma: no cover
    logger.info("autocsr arq worker shutdown")


class WorkerSettings:  # pragma: no cover - executed only by arq cli
    """arq WorkerSettings class. Pass to ``arq.worker.create_worker``."""

    functions = _collect_handlers()
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    keep_result_forever = False
    keep_result = 3600
    job_timeout = 60 * 60          # 1h hard cap per job
    max_jobs = 4
    health_check_interval = 30

    @classmethod
    def get_redis_settings(cls):
        return _redis_settings()

    # arq reads `redis_settings` as a class attribute — provide it lazily.
    @property
    def redis_settings(self):  # type: ignore[override]
        return _redis_settings()
