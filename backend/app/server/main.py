"""FastAPI entrypoint for AutoCSR backend.

Run: uvicorn app.server.main:app --port 8766
"""
from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import summary as config_summary
from app.server.routes import health, llm_ping, projects

logger = logging.getLogger("autocsr")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


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

    # Also mount /health at the root for naive load balancers / smoke checks.
    app.include_router(health.router)
    app.include_router(llm_ping.router)

    @app.on_event("startup")
    async def _log_startup() -> None:
        logger.info("AutoCSR backend starting. settings: %s",
                    json.dumps(config_summary(), ensure_ascii=False))

    return app


app = create_app()
