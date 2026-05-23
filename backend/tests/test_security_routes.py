from __future__ import annotations

import json
import sys
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


def _seed_project(tmp_path: Path, pid: str = "p_sec", uid: str = "u_owner") -> None:
    from app.auth.models import User, upsert_user
    from app.projects.manager import ensure_owner_member

    (tmp_path / "projects" / pid / "raw").mkdir(parents=True, exist_ok=True)
    (tmp_path / "projects.json").write_text(
        json.dumps([
            {
                "id": pid,
                "name": "Security Test",
                "principle_id": "ich_e3",
                "created_at": "2026-05-23T00:00:00+00:00",
                "status": "draft",
                "tenant_id": "default",
                "created_by": uid,
            }
        ]),
        encoding="utf-8",
    )
    upsert_user(User(id=uid, email="owner@example.test", tenant_id="default"))
    ensure_owner_member(pid, "default", uid)


def test_upload_filename_is_sanitized_and_authorized(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)

    response = client.post(
        "/api/projects/p_sec/upload",
        headers={"X-User-Id": "u_owner"},
        files=[("files", ("../../escape.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 200, response.text
    uploaded = response.json()["uploaded"][0]
    assert uploaded["filename"] == "escape.txt"
    stored = Path(uploaded["stored_path"]).resolve()
    raw_root = (tmp_path / "projects" / "p_sec" / "raw").resolve()
    stored.relative_to(raw_root)
    assert not (tmp_path / "projects" / "escape.txt").exists()


def test_upload_requires_write_permission(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)

    response = client.post(
        "/api/projects/p_sec/upload",
        headers={"X-User-Id": "u_viewer"},
        files=[("files", ("ok.txt", b"hello", "text/plain"))],
    )

    assert response.status_code == 403


def test_sandbox_rejects_additional_paths_outside_project(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("secret\n", encoding="utf-8")

    response = client.post(
        "/api/projects/p_sec/sandbox/run",
        headers={"X-User-Id": "u_owner"},
        json={
            "code": "print('ok')",
            "additional_data_paths": [str(outside)],
        },
    )

    assert response.status_code == 400


def test_ask_rejects_parquet_paths_outside_project(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_text("USUBJID,AVAL\nS1,1\n", encoding="utf-8")

    response = client.post(
        "/api/projects/p_sec/ask",
        headers={"X-User-Id": "u_owner"},
        json={"query": "summarize", "parquet_paths": [str(outside)]},
    )

    assert response.status_code == 400
    assert "outside project" in response.text


def test_signature_signer_comes_from_authenticated_user(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _seed_project(tmp_path)

    response = client.post(
        "/api/projects/p_sec/sign",
        headers={"X-User-Id": "u_owner"},
        json={
            "artifact_type": "report",
            "artifact_id": "draft",
            "signer": "attacker",
            "reason": "approval",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["signer"] == "u_owner"
