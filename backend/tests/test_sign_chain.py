"""Sign-chain ordering tests (M17)."""
from __future__ import annotations

import pytest


@pytest.fixture()
def temp_project(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    from app.collab import tasks as _tasks
    monkeypatch.setattr(_tasks, "data_dir", lambda: tmp_path)
    pid = "sc_test"
    (tmp_path / "projects" / pid).mkdir(parents=True)
    return pid, tmp_path


def _make_task(pid: str):
    from app.collab.tasks import create_task
    return create_task(pid, assignee="reviewer", creator="test",
                        body="signature workflow demo", title="t1")


def test_init_creates_default_standard_chain(temp_project):
    pid, _ = temp_project
    task = _make_task(pid)
    from app.collab.sign_chain import DEFAULT_STANDARD_CHAIN, init_chain
    updated = init_chain(pid, task.id)
    assert updated.sign_chain is not None
    roles = [s["role"] for s in updated.sign_chain]
    assert roles == DEFAULT_STANDARD_CHAIN


def test_advance_chain_rejects_out_of_order(temp_project):
    pid, _ = temp_project
    task = _make_task(pid)
    from app.collab.sign_chain import (
        OutOfOrderError, advance_chain, init_chain,
    )
    init_chain(pid, task.id)
    with pytest.raises(OutOfOrderError):
        # Skip past the first (statistician) step
        advance_chain(pid, task.id, role="medical",
                       signer_user_id="med_user")


def test_advance_chain_signs_in_order(temp_project):
    pid, _ = temp_project
    task = _make_task(pid)
    from app.collab.sign_chain import advance_chain, get_chain, init_chain
    init_chain(pid, task.id)
    step = advance_chain(pid, task.id, role="statistician",
                          signer_user_id="stat_user", reason="ok")
    assert step.status == "signed"
    assert step.signer_user_id == "stat_user"
    chain = get_chain(pid, task.id)
    assert chain is not None
    pendings = [s for s in chain if s.status == "pending"]
    assert len(pendings) == 3
