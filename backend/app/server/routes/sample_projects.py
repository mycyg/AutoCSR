"""Sample-project routes (M20 v2.2).

  GET  /api/sample_projects                        — list 5 domains
  POST /api/projects/from_sample/{domain}          — one-click create + bootstrap

The created project gets ADaM parquets pre-staged in its ``processed/`` dir
and a background outline build kicked off using the domain principle.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.projects.sample_projects import (
    create_from_sample,
    list_sample_domains,
)

logger = logging.getLogger("autocsr.routes.sample_projects")
router = APIRouter(tags=["projects"])


@router.get("/sample_projects")
def list_endpoint() -> list[dict[str, Any]]:
    return list_sample_domains()


@router.post("/projects/from_sample/{domain}", status_code=201)
def create_from_sample_endpoint(domain: str,
                                  body: dict = Body(default_factory=dict)
                                  ) -> dict[str, Any]:
    name = (body or {}).get("name")
    schedule_outline = bool((body or {}).get("schedule_outline", True))
    try:
        return create_from_sample(domain, name=name,
                                    schedule_outline=schedule_outline)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:        # noqa: BLE001
        logger.exception("from_sample failed")
        raise HTTPException(status_code=500,
                             detail=f"from_sample failed: {e}")
