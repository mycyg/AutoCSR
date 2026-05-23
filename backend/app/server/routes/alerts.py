"""Global alert aggregator (M11).

Pulls together the various "you should look at this" signals into a
single, paginatable feed for the GlobalAlertBar:

  * DataProfile anomalies   (cleansing — null / outlier / encoding / PII)
  * PII not hashed          (cleansing pipeline missing hash_pii applied)
  * Low-confidence StatBlock (result_json.confidence < 0.7)
  * Writer errors           (SectionDraft with status='error')
  * Reviewer errors/warns   (latest ReviewResult)

In-memory cache: a per-project dict is invalidated on cleansing.apply_done,
review.done, writer.report_done. The cache lives in the module global
``_CACHE`` so any worker importing this module can ``invalidate(pid)`` to
mark it stale.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException

from app.agents.reviewer_agent import load_latest as load_latest_review
from app.analysis.store import get as get_stat, list_blocks as list_stat_blocks
from app.cleansing.pipeline_io import load_proposals
from app.cleansing.profiler import detect_anomalies
from app.config import data_dir
from app.ingestion.orchestrator import load_entries, load_result
from app.report.store import list_drafts

logger = logging.getLogger("autocsr.routes.alerts")
router = APIRouter(tags=["review"])

# project_id -> {"counts": {...}, "items": [...]}
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


def invalidate(project_id: str) -> None:
    """Drop any cached aggregation for one project. Safe from any thread."""
    with _CACHE_LOCK:
        _CACHE.pop(project_id, None)


def _aggregate(pid: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    # 1. DataProfile anomalies (per ingested file)
    try:
        entries = load_entries(pid)
    except Exception:
        entries = []
    for entry in entries:
        try:
            result = load_result(pid, entry.file_id)
        except Exception:
            result = None
        if result is None:
            continue
        for profile in result.profiles:
            for a in (profile.anomalies or []):
                items.append({
                    "severity": a.severity,
                    "source": "cleansing.profile",
                    "message": a.message,
                    "link": f"/p/{pid}/cleanse?file_id={entry.file_id}",
                    "file_id": entry.file_id,
                    "column": a.column,
                })
            # If the cached profile lacks anomalies (older ingest), compute
            # them on the fly so we still see the signal.
            if not profile.anomalies:
                for a in detect_anomalies(profile):
                    items.append({
                        "severity": a.severity,
                        "source": "cleansing.profile",
                        "message": a.message,
                        "link": f"/p/{pid}/cleanse?file_id={entry.file_id}",
                        "file_id": entry.file_id,
                        "column": a.column,
                    })

    # 2. PII not hashed — proposals with type=hash_pii but status != applied
    try:
        proposals = load_proposals(pid)
    except Exception:
        proposals = []
    for p in proposals:
        if p.type == "hash_pii" and p.status not in ("applied",):
            items.append({
                "severity": "warn",
                "source": "cleansing.pii",
                "message": f"列 {','.join(p.target_columns)} 的 PII 哈希尚未应用",
                "link": f"/p/{pid}/cleanse?file_id={p.file_id}",
                "file_id": p.file_id,
            })

    # 3. Low-confidence StatBlocks
    try:
        stat_index = list_stat_blocks(pid)
    except Exception:
        stat_index = []
    for s in stat_index:
        block = None
        try:
            block = get_stat(pid, s["id"])
        except Exception:
            block = None
        if block is None:
            continue
        rj = block.result_json or {}
        conf = rj.get("confidence")
        if isinstance(conf, (int, float)) and conf < 0.7:
            items.append({
                "severity": "info",
                "source": "analysis.confidence",
                "message": f"StatBlock {block.title} 置信度仅 {conf:.2f}，请人工核对。",
                "link": f"/p/{pid}/analyze?stat_id={block.id}",
                "stat_id": block.id,
            })

    # 4. Writer errors
    try:
        drafts = list_drafts(pid)
    except Exception:
        drafts = []
    for d in drafts:
        if d.status == "error":
            items.append({
                "severity": "error",
                "source": "writer.section",
                "message": f"章节 {d.node_id} 「{d.title}」 写作失败",
                "link": f"/p/{pid}/report?node_id={d.node_id}",
                "node_id": d.node_id,
            })

    # 5. Latest review issues (errors + warns; info too noisy here)
    latest = load_latest_review(pid)
    if latest is not None:
        for iss in latest.issues:
            if iss.ignored:
                continue
            if iss.severity not in ("error", "warn"):
                continue
            items.append({
                "severity": iss.severity,
                "source": f"review.{iss.checker}",
                "message": iss.message,
                "link": f"/p/{pid}/review#issue-{iss.id}",
                "node_id": (iss.location.node_id if iss.location else None),
            })

    counts = {"error": 0, "warn": 0, "info": 0}
    for it in items:
        sev = it.get("severity", "info")
        if sev in counts:
            counts[sev] += 1
    return {"counts": counts, "items": items}


@router.get("/projects/{pid}/alerts")
def get_alerts(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    with _CACHE_LOCK:
        cached = _CACHE.get(pid)
    if cached is not None:
        return cached
    payload = _aggregate(pid)
    with _CACHE_LOCK:
        _CACHE[pid] = payload
    return payload


@router.post("/projects/{pid}/alerts/invalidate")
def post_invalidate(pid: str) -> dict[str, bool]:
    _ensure_project(pid)
    invalidate(pid)
    return {"ok": True}
