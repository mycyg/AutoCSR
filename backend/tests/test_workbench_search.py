from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    from app import config as _cfg
    from app.config import project_config as _project_config

    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("app.") and hasattr(module, "data_dir"):
            monkeypatch.setattr(module, "data_dir", lambda: tmp_path, raising=False)
    _cfg._CACHE = None
    _project_config._CACHE.clear()

    from app.server.main import create_app

    return TestClient(create_app())


def _seed_project(tmp_path: Path, pid: str = "p_ui", uid: str = "u_owner") -> None:
    from app.auth.models import User, upsert_user
    from app.projects.manager import ensure_owner_member

    for sub in ("raw", "processed", "chapters", "exports"):
        (tmp_path / "projects" / pid / sub).mkdir(parents=True, exist_ok=True)
    (tmp_path / "projects.json").write_text(
        json.dumps([
            {
                "id": pid,
                "name": "Workbench Trial",
                "principle_id": "ich_e3",
                "created_at": "2026-05-23T00:00:00+00:00",
                "status": "draft",
                "tenant_id": "default",
                "created_by": uid,
                "language": "zh",
            }
        ]),
        encoding="utf-8",
    )
    upsert_user(User(id=uid, email="owner@example.test", tenant_id="default"))
    ensure_owner_member(pid, "default", uid)


def _seed_workbench_content(pid: str = "p_ui") -> None:
    from app.agents.reviewer_agent import save_review
    from app.collab.tasks import create_task
    from app.outline.store import save as save_outline
    from app.report.store import save_draft
    from app.schemas.outline import Outline, OutlineNode
    from app.schemas.report import SectionDraft
    from app.schemas.review import Issue, IssueLocation, ReviewResult

    now = datetime.now(timezone.utc)
    outline = Outline(
        project_id=pid,
        principle_id="ich_e3",
        version=1,
        created_at=now,
        updated_at=now,
        root_sections=[
            OutlineNode(id="11.4.2", title="Efficacy results", level=2),
        ],
    )
    save_outline(outline)
    save_draft(pid, SectionDraft(
        node_id="11.4.2",
        title="Efficacy results",
        markdown="## Efficacy results\n\nALT improved versus placebo.",
        word_count=6,
        generated_at=now,
    ))
    create_task(
        pid,
        assignee="demo_reviewer",
        creator="u_owner",
        title="Check ALT table",
        body="Please verify the ALT table.",
        node_id="11.4.2",
        severity="warn",
    )
    save_review(ReviewResult(
        project_id=pid,
        passed=False,
        created_at=now,
        issues=[
            Issue(
                id="issue_alt",
                severity="error",
                checker="numeric",
                message="ALT denominator mismatch",
                suggestion="Recheck source table",
                location=IssueLocation(node_id="11.4.2", char_range=(3, 12)),
            )
        ],
    ))


def test_workbench_aggregates_project_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)
    _seed_workbench_content()

    response = client.get("/api/projects/p_ui/workbench", headers={"X-User-Id": "u_owner"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["name"] == "Workbench Trial"
    assert body["metrics"]["drafts"] == 1
    assert body["metrics"]["open_tasks"] == 1
    assert body["risks"]["error"] == 1
    assert body["tasks"][0]["href"].startswith("/p/p_ui/report?node=11.4.2")


def test_project_search_returns_deep_links(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)
    _seed_workbench_content()

    response = client.get(
        "/api/projects/p_ui/search",
        headers={"X-User-Id": "u_owner"},
        params={"q": "ALT"},
    )

    assert response.status_code == 200, response.text
    hits = response.json()
    assert any(h["type"] == "draft" and "node=11.4.2" in h["href"] for h in hits)
    assert any(h["type"] == "review" and "panel=comments" in h["href"] for h in hits)


def test_task_event_normalizer_keeps_legacy_writer_events():
    from app.server.task_events import normalize_task_event

    event = normalize_task_event("p_ui", "writer.section_done", {
        "node_id": "11.4.2",
        "index": 2,
        "total": 4,
    })

    assert event is not None
    assert event.task_id == "p_ui:writer"
    assert event.status == "running"
    assert event.progress == 50
    assert event.href == "/p/p_ui/report?node=11.4.2&panel=status"


def test_multi_export_rejects_unsupported_hallucination_warning_format(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)

    response = client.post(
        "/api/projects/p_ui/export/pdf",
        headers={"X-User-Id": "u_owner"},
        json={"include_hallucination_warnings": True},
    )

    assert response.status_code == 400
    assert "include_hallucination_warnings" in response.text
