"""Chart recommendation route (M20 v2.2).

  POST /api/projects/{pid}/chart/recommend
      body: {stat_id?: str, stat_block?: dict}
      returns: ChartRecommendation
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.agents.chart_selector import recommend_chart
from app.analysis.store import get as get_stat
from app.config import data_dir

logger = logging.getLogger("autocsr.routes.chart_recommend")
router = APIRouter(tags=["analysis"])


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/chart/recommend")
def recommend_endpoint(pid: str,
                         body: dict = Body(default_factory=dict)
                         ) -> dict[str, Any]:
    _ensure_project(pid)
    sb_in: Any = (body or {}).get("stat_block")
    sid = str((body or {}).get("stat_id") or "").strip()
    if not sb_in and not sid:
        raise HTTPException(status_code=400,
                             detail="provide stat_id or stat_block")
    if sb_in is None:
        sb = get_stat(pid, sid)
        if sb is None:
            raise HTTPException(status_code=404,
                                 detail=f"stat_block {sid} not found")
        sb_dict = sb.model_dump()
    else:
        sb_dict = sb_in

    try:
        rec = recommend_chart(sb_dict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:        # noqa: BLE001
        logger.exception("chart recommend failed")
        raise HTTPException(status_code=500,
                             detail=f"chart recommend failed: {e}")
    return rec.to_dict()
