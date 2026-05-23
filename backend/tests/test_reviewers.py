"""Reviewer + multi-reviewer unit tests with mocked drafts (M17)."""
from __future__ import annotations

import asyncio
import datetime as _dt
from pathlib import Path

import pytest

from app.agents.reviewers.completeness import CompletenessReviewer
from app.agents.reviewers.medical import MedicalReviewer
from app.agents.reviewers.regulatory import RegulatoryReviewer
from app.agents.reviewers.statistician import StatisticianReviewer
from app.schemas.agent import AgentInput
from app.schemas.report import SectionDraft
from app.schemas.review import ReviewResult


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture()
def isolated_project(tmp_path, monkeypatch):
    """Redirect data_dir() so each test gets a clean project tree.

    ``app.config.data_dir`` is imported into many modules at startup,
    so we patch the binding in every concrete consumer the reviewer
    fan-out touches.
    """
    monkeypatch.setenv("AUTOCSR_DATA_DIR", str(tmp_path))
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    # Re-bind data_dir inside modules that did `from app.config import data_dir`
    for module_path in (
        "app.report.store",
        "app.analysis.store",
        "app.outline.store",
        "app.collab.tasks",
        "app.cleansing.auditor",
    ):
        try:
            mod = __import__(module_path, fromlist=["data_dir"])
            if hasattr(mod, "data_dir"):
                monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
        except Exception:
            pass
    pid = "rev_test"
    (tmp_path / "projects" / pid / "chapters").mkdir(parents=True)
    return pid, tmp_path


def _write_draft(tmp_path: Path, pid: str, node_id: str, markdown: str) -> None:
    d = SectionDraft(
        node_id=node_id, title=f"Node {node_id}", markdown=markdown,
        generated_at=_dt.datetime.now(_dt.timezone.utc),
    )
    out = tmp_path / "projects" / pid / "chapters" / f"{node_id}.json"
    out.write_text(d.model_dump_json(), encoding="utf-8")


def test_statistician_flags_pvalue_without_ci(isolated_project):
    pid, tmp = isolated_project
    _write_draft(tmp, pid, "11.4.1.1",
                  "结果表明 P=0.012，提示有统计学差异。")
    out = _run(StatisticianReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    # The statistician emits a Chinese-language warning about missing CI.
    assert any("置信区间" in i.message or "CI" in i.message for i in rr.issues)


def test_statistician_passes_on_clean_text(isolated_project):
    pid, tmp = isolated_project
    _write_draft(tmp, pid, "11.4.1.1",
                  "结果为 HR=0.85（95% CI: 0.70-1.02），未达统计学显著。")
    out = _run(StatisticianReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    # Always returns at least one info finding on clean drafts.
    assert all(i.severity != "error" for i in rr.issues)


def test_medical_reviewer_returns_result(isolated_project):
    pid, _ = isolated_project
    out = _run(MedicalReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    assert isinstance(rr.issues, list)


def test_regulatory_reviewer_returns_result(isolated_project):
    pid, _ = isolated_project
    out = _run(RegulatoryReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    assert isinstance(rr.issues, list)


def test_completeness_flags_missing_outline(isolated_project):
    pid, _ = isolated_project
    out = _run(CompletenessReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    assert rr.passed is False
    assert any("outline" in i.message.lower() for i in rr.issues)


def test_completeness_clean_when_outline_filled(isolated_project, monkeypatch):
    pid, tmp = isolated_project

    from app.agents.reviewers import completeness as comp_mod
    from app.schemas.outline import Outline, OutlineNode
    leaf = OutlineNode(id="X.1", title="X1", status="done")
    o = Outline(
        project_id=pid, principle_id="ich_e3", version=1,
        root_sections=[leaf],
        created_at=_dt.datetime.now(_dt.timezone.utc),
        updated_at=_dt.datetime.now(_dt.timezone.utc),
    )
    # Patch all the symbols the completeness reviewer pulled into its
    # module namespace at import time.
    monkeypatch.setattr(comp_mod.outline_store, "load", lambda p: o)
    monkeypatch.setattr(comp_mod, "load_principle",
                        lambda pid: (_ for _ in ()).throw(FileNotFoundError("none")))
    monkeypatch.setattr(comp_mod, "load_draft", lambda p, nid: SectionDraft(
        node_id=nid, title=nid, markdown="Plenty of body text.",
        generated_at=_dt.datetime.now(_dt.timezone.utc),
    ))
    out = _run(CompletenessReviewer().run(AgentInput(project_id=pid)))
    rr = ReviewResult.model_validate(out.result)
    # No principle => no missing-required errors; draft is non-empty.
    assert all(i.severity != "error" for i in rr.issues)
