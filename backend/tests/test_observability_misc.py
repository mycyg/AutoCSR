"""Smoke tests for observability + pagination + i18n + audit rotation (M17)."""
from __future__ import annotations

import gzip
from datetime import datetime, timezone

import pytest

from app.audit.rotation import rotate_if_needed
from app.i18n.format import (
    format_date, format_number, format_p_value, format_percent, format_unit,
)
from app.observability import error_hook
from app.queue import checkpoint as cp
from app.server.middlewares.pagination import paginate


# --------------------------------------------------------------------- error_hook

def test_register_dispatch_unregister_sink():
    captured: list[tuple] = []
    sink = lambda src, exc, **ctx: captured.append((src, type(exc).__name__, ctx))
    error_hook.clear_error_sinks()
    error_hook.register_error_sink(sink)
    n = error_hook.dispatch_error("unit", ValueError("boom"), pid="p1")
    assert n == 1 and captured == [("unit", "ValueError", {"pid": "p1"})]
    assert error_hook.unregister_error_sink(sink) is True
    assert error_hook.dispatch_error("unit", ValueError("again")) == 0


def test_dispatch_with_no_sinks_returns_zero():
    error_hook.clear_error_sinks()
    assert error_hook.dispatch_error("x", RuntimeError("y")) == 0


# --------------------------------------------------------------------- pagination

def test_paginate_returns_full_list_when_no_args():
    body = paginate([1, 2, 3])
    assert body["items"] == [1, 2, 3] and body["total"] == 3


def test_paginate_slices_correctly():
    body = paginate(list(range(10)), offset=3, limit=4)
    assert body["items"] == [3, 4, 5, 6]
    assert body["total"] == 10
    assert body["offset"] == 3 and body["limit"] == 4


def test_paginate_rejects_invalid_offset():
    with pytest.raises(ValueError):
        paginate([1], offset=-1, limit=1)


# --------------------------------------------------------------------- i18n

def test_format_number_renders_thousands():
    s = format_number(1234567.89, locale="zh", precision=2)
    assert "1,234,567" in s.replace(" ", "")


def test_format_percent_returns_string_with_percent():
    s = format_percent(0.123, locale="zh", precision=1)
    assert s.endswith("%") or "%" in s


def test_format_p_value_uses_below_001_for_tiny_values():
    assert "0.001" in format_p_value(1e-5)


def test_format_unit_converts_mg_dl_to_mmol():
    # 100 mg/dL glucose -> 5.55 mmol/L
    s = format_unit(100.0, "mg/dl", locale="en", precision=2)
    assert "mmol/L" in s
    assert "5.55" in s


def test_format_date_shanghai_zh():
    ts = datetime(2026, 5, 23, 4, 30, tzinfo=timezone.utc)
    out = format_date(ts, locale="zh", tz="Asia/Shanghai")
    assert "2026" in out


# --------------------------------------------------------------------- checkpoint

@pytest.fixture()
def tmp_data(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    from app.queue import checkpoint as _cp_mod
    monkeypatch.setattr(_cp_mod, "data_dir", lambda: tmp_path)
    (tmp_path / "projects" / "cpr").mkdir(parents=True)
    return "cpr", tmp_path


def test_checkpoint_round_trip(tmp_data):
    pid, _ = tmp_data
    cp.write_checkpoint(pid, "tid1", kind="report.generate", total=3)
    cp.record_progress(pid, "tid1", "node1")
    cp.record_progress(pid, "tid1", "node2")
    loaded = cp.load_checkpoint(pid, "tid1")
    assert loaded is not None
    assert set(loaded.completed_items) == {"node1", "node2"}
    assert cp.remaining_items(pid, "tid1",
                                ["node1", "node2", "node3"]) == ["node3"]
    assert cp.resume_from_checkpoint(pid, "tid1") is True
    cp.mark_done(pid, "tid1")
    assert cp.load_checkpoint(pid, "tid1").status == "done"


# --------------------------------------------------------------------- rotation

def test_rotate_if_needed_archives_oversize_shard(tmp_data):
    pid, tmp = tmp_data
    shard = tmp / "projects" / pid / "audit" / "2026-05.jsonl"
    shard.parent.mkdir(parents=True)
    body = b"{\"line\": 1}\n" * 1000
    shard.write_bytes(body)
    archive = rotate_if_needed(shard, threshold_bytes=100)  # force rotation
    assert archive is not None and archive.exists()
    assert shard.read_bytes() == b""
    with gzip.open(archive, "rb") as fh:
        assert fh.read().startswith(b"{\"line\":")


def test_rotate_no_op_when_under_threshold(tmp_data):
    pid, tmp = tmp_data
    shard = tmp / "projects" / pid / "audit" / "2026-06.jsonl"
    shard.parent.mkdir(parents=True)
    shard.write_bytes(b"{}\n")
    assert rotate_if_needed(shard, threshold_bytes=10_000_000) is None
