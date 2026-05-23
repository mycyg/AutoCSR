"""FastAPI entrypoint for AutoCSR backend.

Run: uvicorn app.server.main:app --port 8766
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import summary as config_summary
from app.observability.logger import configure_logging, get_logger
from app.audit.middleware import AuditMiddleware
from app.server.routes import (
    admin, alerts, comments, diff, health, import_csr, llm_ping, plan, projects,
    review, upload, ingest, cleansing, corpus, principles,
    analysis, outline, report, chat, export, sandbox,
    # V2-E M14
    coding, analysis_advanced,
    # V2-F M15+M16
    audit, collab, compliance, multi_review,
    # V3-A M17 — hallucination + eCTD
    hallucination, ectd,
    # M19 — project backup + restore
    backup,
    # M20 (v2.2) — sample projects + literature + polish + chart + formula
    sample_projects, literature_search, polish, chart_recommend,
    # M21 (v2.3) — JWT auth + tenants + reverse import + advanced viz
    auth as auth_routes,
    import_aux,
    analysis_viz,
    dashboard as dashboard_routes,
    workbench,
)
from app.server.ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
configure_logging()
logger = get_logger("autocsr.server")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AutoCSR API",
        version="1.0.0",
        description=(
            "Open-source ICH E3 / NMPA Clinical Study Report (CSR) generation "
            "platform. The HTTP surface mirrors the production pipeline: "
            "ingestion → cleansing → analysis → outline → writer agent → "
            "harmonize → review → audit / e-sign → DOCX / eCTD export."
        ),
        contact={
            "name": "AutoCSR Maintainers",
            "url": "https://github.com/autocsr/autocsr",
        },
        license_info={
            "name": "Apache-2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0",
        },
        openapi_tags=[
            {"name": "health", "description": "Liveness + LLM ping."},
            {"name": "projects", "description": "Project CRUD + tagging + archive."},
            {"name": "ingest", "description": "Upload + 6-worker ingestion pipeline."},
            {"name": "cleansing", "description": "Proposal workbench, transformer, audit, pipeline IO."},
            {"name": "analysis", "description": "Descriptive / inferential / survival / safety + advanced stats + TLF zip."},
            {"name": "outline", "description": "ICH E3 outline builder + stat_refs binding."},
            {"name": "report", "description": "Writer orchestrator + chat editor + plan-first + harmonize."},
            {"name": "review", "description": "Single + multi reviewer (statistician/medical/regulatory/completeness)."},
            {"name": "export", "description": "DOCX + TLF + eCTD packagers."},
            {"name": "audit", "description": "Append-only hash-chain audit + ed25519 signatures."},
            {"name": "safety", "description": "Hallucination guard + PII scan + redaction."},
            {"name": "collab", "description": "Users + ReviewTasks + Kanban + sign chains."},
            {"name": "admin", "description": "Sandbox + corpus + principles + diagnostics."},
            {"name": "observability", "description": "Prometheus /metrics + error sinks."},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:5174", "http://127.0.0.1:5174",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # M15 — append-only audit chain for every mutation route.
    app.add_middleware(AuditMiddleware)

    # M19 — per-user / per-route rate limit (token bucket fallback when
    # slowapi/Redis are unavailable; deterministic enough for e2e).
    from app.server.middlewares.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)
    from app.server.middlewares.project_access import ProjectAccessMiddleware
    app.add_middleware(ProjectAccessMiddleware)

    # Routes are mounted under /api so the Vite proxy can forward them cleanly.
    app.include_router(health.router, prefix="/api")
    app.include_router(llm_ping.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(ingest.router, prefix="/api")
    app.include_router(cleansing.router, prefix="/api")
    app.include_router(corpus.router, prefix="/api")
    app.include_router(principles.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(outline.router, prefix="/api")
    app.include_router(report.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(sandbox.router, prefix="/api")
    # V2-C M10 + M11
    app.include_router(plan.router, prefix="/api")
    app.include_router(review.router, prefix="/api")
    app.include_router(comments.router, prefix="/api")
    app.include_router(diff.router, prefix="/api")
    app.include_router(alerts.router, prefix="/api")
    # V2-D M13 — CSR reverse-import
    app.include_router(import_csr.router, prefix="/api")
    # V2-E M14 — medical coding + advanced stats + TLF export
    app.include_router(coding.router, prefix="/api")
    app.include_router(analysis_advanced.router, prefix="/api")
    # V2-F M15 — audit trail + e-sig + blinding/lock
    app.include_router(audit.router, prefix="/api")
    app.include_router(compliance.router, prefix="/api")
    # V2-F M16 — multi-reviewer + collab + queue
    app.include_router(multi_review.router, prefix="/api")
    app.include_router(collab.router, prefix="/api")
    # V3-A M17 — hallucination guard + eCTD packager + Prometheus metrics
    app.include_router(hallucination.router, prefix="/api")
    app.include_router(ectd.router, prefix="/api")
    # M19 — project backup + restore
    app.include_router(backup.router, prefix="/api")
    # M20 (v2.2) — sample projects + 4 new AI agent endpoints
    app.include_router(sample_projects.router, prefix="/api")
    app.include_router(literature_search.router, prefix="/api")
    app.include_router(polish.router, prefix="/api")
    app.include_router(chart_recommend.router, prefix="/api")
    # M21 (v2.3) — auth + reverse import + advanced viz + dashboard
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(import_aux.router, prefix="/api")
    app.include_router(analysis_viz.router, prefix="/api")
    app.include_router(dashboard_routes.router, prefix="/api")
    app.include_router(workbench.router, prefix="/api")
    try:
        from app.observability.metrics import router as metrics_router
        app.include_router(metrics_router)
    except Exception as e:  # noqa: BLE001
        logger.warning("metrics_router_unavailable: %s", e)

    # WebSocket hub (no /api prefix — exposed at /ws/{pid})
    app.include_router(ws_router)

    # Also mount /health at the root for naive load balancers / smoke checks.
    app.include_router(health.router)
    app.include_router(llm_ping.router)

    @app.on_event("startup")
    async def _log_startup() -> None:
        logger.info("server.start", settings=config_summary())
        # M21 — make sure the default tenant exists + back-fill tenant_id on
        # any legacy project records. This is idempotent and very cheap.
        try:
            from app.auth.models import ensure_default_tenant
            ensure_default_tenant()
        except Exception as e:  # noqa: BLE001
            logger.warning("default_tenant_init_failed: %s", e)
        try:
            from scripts_helpers.multitenant import backfill_tenant_id
            backfill_tenant_id()
        except Exception as e:  # noqa: BLE001
            logger.debug("backfill_tenant_id_skip: %s", e)

    # M17 — global exception bridge to the pluggable error_hook registry.
    # HTTPException stays untouched so 4xx aren't broadcast as runtime
    # errors; everything else is fanned out.
    from fastapi import HTTPException as _HTTPException
    from fastapi.responses import JSONResponse as _JSONResponse

    @app.exception_handler(Exception)
    async def _bridge_to_sinks(request, exc):  # type: ignore[no-redef]
        if isinstance(exc, _HTTPException):
            raise exc
        try:
            from app.observability.error_hook import dispatch_error
            dispatch_error("server", exc, path=str(request.url.path),
                            method=request.method)
        except Exception:
            pass
        logger.exception("unhandled_server_error path=%s", request.url.path)
        return _JSONResponse(
            status_code=500,
            content={"detail": f"internal error: {type(exc).__name__}"},
        )

    return app


app = create_app()
