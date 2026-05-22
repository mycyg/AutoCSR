"""Per-project configuration.

Lives at ``data/projects/<pid>/config.json``. Fields control runtime
behaviour for that project only — global defaults stay in
``settings.example.yaml`` but per-project knobs let advanced users tune
(e.g. lower max_parallel_writers on a small VPS, switch language for the
docx template, harden sandbox redaction).

Lazy-loaded with a small in-memory cache so we don't re-parse JSON on every
agent call. The cache is invalidated by :func:`save_config`.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import data_dir


class ProjectConfig(BaseModel):
    """User-tunable per-project settings.

    Defaults mirror the behaviour the M1-M5 codebase had hard-coded.
    """
    language: str = "zh"                # "zh" / "en" — affects DOCX template
    docx_template_id: str = "standard"  # picked up by export.docx_builder
    max_parallel_writers: int = 4       # ceiling for writer Semaphore
    max_tool_turns: int = 5             # cap for chat editor tool loops (M6)
    sandbox_enabled: bool = True        # gate on POST /sandbox/run
    sandbox_timeout_s: int = 30
    sandbox_mem_mb: int = 512
    llm_data_redaction: str = "strict"  # "strict" / "off" — passes to ark_client
    pii_strip: bool = True              # extra hash_pii pass on cleansed data

    @classmethod
    def default(cls) -> "ProjectConfig":
        return cls()


_LOCK = threading.RLock()
_CACHE: dict[str, ProjectConfig] = {}


def _config_path(pid: str) -> Path:
    return data_dir() / "projects" / pid / "config.json"


def get_config(pid: str) -> ProjectConfig:
    """Read (and cache) the project config; auto-creates the default file."""
    with _LOCK:
        cached = _CACHE.get(pid)
        if cached is not None:
            return cached
        p = _config_path(pid)
        if not p.exists():
            cfg = ProjectConfig.default()
            _CACHE[pid] = cfg
            return cfg
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            cfg = ProjectConfig.model_validate(raw)
        except (json.JSONDecodeError, Exception):
            cfg = ProjectConfig.default()
        _CACHE[pid] = cfg
        return cfg


def save_config(pid: str, updates: ProjectConfig | dict[str, Any]) -> ProjectConfig:
    """Persist a new config (or partial update). Returns the merged result."""
    with _LOCK:
        current = get_config(pid)
        if isinstance(updates, ProjectConfig):
            merged = updates
        else:
            payload = current.model_dump()
            for k, v in (updates or {}).items():
                if k in payload:
                    payload[k] = v
            merged = ProjectConfig.model_validate(payload)
        p = _config_path(pid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
        _CACHE[pid] = merged
        return merged


def invalidate(pid: str) -> None:
    with _LOCK:
        _CACHE.pop(pid, None)
