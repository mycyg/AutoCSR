"""FastAPI entrypoint for AutoCSR backend.

Run: uvicorn app.server.main:app --port 8766
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import summary as config_summary
from app.observability.logger import configure_logging, get_logger
from app.server.routes import (
    admin, alerts, comments, diff, health, import_csr, llm_ping, plan, projects,
    review, upload, ingest, cleansing, corpus, principles,
    analysis, outline, report, chat, export, sandbox,
)
from app.server.ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
configure_logging()
logger = get_logger("autocsr.server")


def create_app() -> FastAPI:
    app = FastAPI(title="AutoCSR", version="0.1.0")

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

    # WebSocket hub (no /api prefix — exposed at /ws/{pid})
    app.include_router(ws_router)

    # Also mount /health at the root for naive load balancers / smoke checks.
    app.include_router(health.router)
    app.include_router(llm_ping.router)

    @app.on_event("startup")
    async def _log_startup() -> None:
        logger.info("server.start", settings=config_summary())

    return app


app = create_app()
