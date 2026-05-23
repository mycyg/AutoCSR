"""Parent aggregator: run the 3 expert reviewers in parallel (M16)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.reviewers.medical import MedicalReviewer
from app.agents.reviewers.regulatory import RegulatoryReviewer
from app.agents.reviewers.statistician import StatisticianReviewer
from app.config import data_dir
from app.schemas.agent import AgentInput
from app.schemas.review import ReviewResult
from app.server.ws import publish

logger = logging.getLogger("autocsr.agents.reviewers.multi")

_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


class MultiReviewResult(BaseModel):
    project_id: str
    statistician: ReviewResult
    medical: ReviewResult
    regulatory: ReviewResult
    combined_count: dict[str, int] = Field(default_factory=dict)
    created_at: datetime


def _multi_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "multi_reviews"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def _run_one(agent_cls, pid: str, label: str) -> ReviewResult:
    await publish(pid, "review.checker_start", {"name": label})
    try:
        agent = agent_cls()
        ao = await agent.run(AgentInput(project_id=pid))
        rr = ReviewResult.model_validate(ao.result)
    except Exception as e:  # noqa: BLE001
        logger.exception("reviewer %s failed", label)
        rr = ReviewResult(
            project_id=pid, passed=False, issues=[],
            checkers=[], created_at=datetime.now(timezone.utc),
        )
    await publish(pid, "review.checker_done", {
        "name": label,
        "issues_count": sum(1 for i in rr.issues if not i.ignored),
    })
    return rr


async def run_multi_review(project_id: str) -> MultiReviewResult:
    await publish(project_id, "review.start", {
        "checkers": ["statistician", "medical", "regulatory"],
        "mode": "multi",
    })
    stat_rr, med_rr, reg_rr = await asyncio.gather(
        _run_one(StatisticianReviewer, project_id, "statistician"),
        _run_one(MedicalReviewer, project_id, "medical"),
        _run_one(RegulatoryReviewer, project_id, "regulatory"),
    )
    combined = {
        "errors": sum(
            sum(1 for i in r.issues if i.severity == "error" and not i.ignored)
            for r in (stat_rr, med_rr, reg_rr)
        ),
        "warns": sum(
            sum(1 for i in r.issues if i.severity == "warn" and not i.ignored)
            for r in (stat_rr, med_rr, reg_rr)
        ),
        "infos": sum(
            sum(1 for i in r.issues if i.severity == "info" and not i.ignored)
            for r in (stat_rr, med_rr, reg_rr)
        ),
    }
    result = MultiReviewResult(
        project_id=project_id,
        statistician=stat_rr,
        medical=med_rr,
        regulatory=reg_rr,
        combined_count=combined,
        created_at=datetime.now(timezone.utc),
    )
    save_multi(result)
    await publish(project_id, "review.done", {
        "mode": "multi",
        "n_errors": combined["errors"],
        "n_warns": combined["warns"],
        "n_infos": combined["infos"],
    })
    return result


def save_multi(result: MultiReviewResult) -> None:
    pid = result.project_id
    payload = json.loads(result.model_dump_json())
    with _plock(pid):
        stamp = result.created_at.strftime("%Y%m%d_%H%M%S_%f")
        (_multi_dir(pid) / f"{stamp}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (_multi_dir(pid) / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_latest_multi(pid: str) -> MultiReviewResult | None:
    p = _multi_dir(pid) / "latest.json"
    if not p.exists():
        return None
    try:
        return MultiReviewResult.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None
