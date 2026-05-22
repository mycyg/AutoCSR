"""Runtime configuration loader for AutoCSR.

Merges `settings.yaml` (gitignored, user-local) on top of `settings.example.yaml`
(committed default). Environment variables can override sensitive fields
without writing them to disk.

Public surface:
  settings(refresh=False) -> dict
  data_dir() -> Path                 # resolves server.data_dir relative to repo
  save(new_settings) -> None         # persists settings.yaml (secrets stripped)
"""
from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).parent
_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# Sensitive fields: env > yaml. Keep narrow until vision_llm/embedding land in M2+.
_ENV_OVERRIDES: list[tuple[str, list[str]]] = [
    ("LLM_API_KEY", ["llm", "api_key"]),
    ("LLM_BASE_URL", ["llm", "base_url"]),
    ("LLM_MODEL", ["llm", "model"]),
]


def _apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    for env_key, path in _ENV_OVERRIDES:
        val = os.environ.get(env_key)
        if not val:
            continue
        node: Any = cfg
        for k in path[:-1]:
            if not isinstance(node.get(k), dict):
                node[k] = {}
            node = node[k]
        node[path[-1]] = val
    return cfg


def _strip_secrets(cfg: dict[str, Any]) -> dict[str, Any]:
    """Before persisting, blank out fields that came from environment."""
    out = copy.deepcopy(cfg)
    for env_key, path in _ENV_OVERRIDES:
        if not os.environ.get(env_key):
            continue
        node: Any = out
        for k in path[:-1]:
            if not isinstance(node.get(k), dict):
                node = None
                break
            node = node[k]
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = ""
    return out


def settings(refresh: bool = False) -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None and not refresh:
            return _CACHE
        example_path = _CONFIG_DIR / "settings.example.yaml"
        example = yaml.safe_load(example_path.read_text(encoding="utf-8")) or {}
        local_path = _CONFIG_DIR / "settings.yaml"
        local = (
            yaml.safe_load(local_path.read_text(encoding="utf-8")) or {}
            if local_path.exists()
            else {}
        )
        merged = _deep_merge(example, local)
        _CACHE = _apply_env_overrides(merged)
        return _CACHE


def save(new_settings: dict[str, Any]) -> None:
    """Persist user-mutable settings.yaml; env-sourced secrets are blanked."""
    safe = _strip_secrets(new_settings)
    with _LOCK:
        (_CONFIG_DIR / "settings.yaml").write_text(
            yaml.safe_dump(safe, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        settings(refresh=True)


def data_dir() -> Path:
    """Resolve `server.data_dir` to an absolute path; create if missing."""
    s = settings()
    raw = s.get("server", {}).get("data_dir", "./data")
    if os.path.isabs(raw):
        p = Path(raw)
    else:
        # config/ -> app/ -> backend/ -> repo root
        p = (_CONFIG_DIR.parent.parent.parent / raw).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def summary() -> dict[str, Any]:
    """Compact dict for startup logging — no secrets."""
    s = settings()
    llm = s.get("llm") or {}
    srv = s.get("server") or {}
    return {
        "llm.base_url": llm.get("base_url"),
        "llm.model": llm.get("model"),
        "llm.api_key_set": bool(llm.get("api_key")),
        "server.host": srv.get("host"),
        "server.port": srv.get("port"),
        "server.data_dir": str(data_dir()),
    }
