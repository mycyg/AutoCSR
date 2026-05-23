"""eCTD packager structural tests (M17)."""
from __future__ import annotations

import zipfile

import pytest


@pytest.fixture()
def temp_project(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    from app.export import ectd_packager as _pkg
    monkeypatch.setattr(_pkg, "data_dir", lambda: tmp_path)
    from app.collab import tasks as _tasks
    monkeypatch.setattr(_tasks, "data_dir", lambda: tmp_path)
    pid = "ectd_test"
    pdir = tmp_path / "projects" / pid
    (pdir / "exports").mkdir(parents=True)
    # Drop a fake docx + tlf zip into exports so the packager has
    # something to bundle.
    (pdir / "exports" / "csr_x.docx").write_bytes(b"PK\x03\x04dummy-docx")
    inner_zip = pdir / "exports" / "tlf_run1.zip"
    with zipfile.ZipFile(inner_zip, "w") as zf:
        zf.writestr("tables/t14_1.csv", "param,value\nn,42\n")
        zf.writestr("define.xml", "<?xml version='1.0'?><Define/>")
    # Also a projects.json so study_id picks up the project name
    (tmp_path / "projects.json").write_text(
        '[{"id":"ectd_test","name":"My Cool Study"}]',
        encoding="utf-8",
    )
    return pid, tmp_path


def test_package_ectd_writes_expected_directories(temp_project):
    pid, tmp = temp_project
    from app.export.ectd_packager import package_ectd
    out = package_ectd(pid)
    assert out.exists()
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
    assert any(n.startswith("m1/m1.2-cover.pdf") for n in names)
    assert any(n.endswith("/csr.docx") for n in names)
    assert any(n.endswith("/tlf.zip") for n in names)
    assert any(n.endswith("/define.xml") for n in names)
    assert any(n.endswith("/sign_chain.json") for n in names)
    assert any(n.endswith("/manifest.json") for n in names)


def test_package_ectd_uses_study_id_from_project_name(temp_project):
    pid, _ = temp_project
    from app.export.ectd_packager import package_ectd
    out = package_ectd(pid)
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
    # 'My Cool Study' -> 'my-cool-study'
    assert any("/my-cool-study/" in n for n in names), names


def test_package_ectd_missing_project_raises(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    from app.export.ectd_packager import package_ectd
    with pytest.raises(FileNotFoundError):
        package_ectd("does_not_exist")
