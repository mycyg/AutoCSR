"""M21 — interactive dashboard composer.

A *dashboard* is just a saved grid layout: each cell points at one
existing StatBlock (referenced by ``stat_id``) and carries the
position/size hints used by the frontend's grid renderer.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import data_dir

logger = logging.getLogger("autocsr.analysis.dashboard")

_LOCK = threading.RLock()


class ChartPosition(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 6
    h: int = 4


class ChartCell(BaseModel):
    cell_id: str = Field(default_factory=lambda: "c_" + uuid.uuid4().hex[:8])
    stat_id: str
    title: str = ""
    chart_type: str = "auto"  # 'auto' | 'km_with_risk' | 'bland_altman' | ...
    position: ChartPosition = Field(default_factory=ChartPosition)


class DashboardConfig(BaseModel):
    id: str = Field(default_factory=lambda: "d_" + uuid.uuid4().hex[:8])
    project_id: str
    name: str = "Untitled Dashboard"
    layout: list[ChartCell] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _dashboard_path(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "dashboards.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def list_dashboards(pid: str) -> list[DashboardConfig]:
    p = _dashboard_path(pid)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [DashboardConfig.model_validate(d) for d in (raw if isinstance(raw, list) else [])]
    except Exception:
        return []


def save_dashboard(dashboard: DashboardConfig) -> DashboardConfig:
    pid = dashboard.project_id
    with _LOCK:
        items = list_dashboards(pid)
        dashboard = dashboard.model_copy(
            update={"updated_at": datetime.now(timezone.utc)},
        )
        for i, d in enumerate(items):
            if d.id == dashboard.id:
                items[i] = dashboard
                break
        else:
            items.append(dashboard)
        _dashboard_path(pid).write_text(
            json.dumps([json.loads(d.model_dump_json()) for d in items],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dashboard


def delete_dashboard(pid: str, dashboard_id: str) -> bool:
    with _LOCK:
        items = list_dashboards(pid)
        keep = [d for d in items if d.id != dashboard_id]
        if len(keep) == len(items):
            return False
        _dashboard_path(pid).write_text(
            json.dumps([json.loads(d.model_dump_json()) for d in keep],
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True


def build_dashboard(project_id: str, name: str,
                     layout: list[dict[str, Any]]) -> DashboardConfig:
    cells = [ChartCell.model_validate(c) for c in (layout or [])]
    dash = DashboardConfig(project_id=project_id, name=name or "Untitled",
                            layout=cells)
    return save_dashboard(dash)
