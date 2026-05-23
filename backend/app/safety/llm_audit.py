"""Per-project LLM call log (M15).

Lands in ``data/projects/<pid>/llm_calls/<yyyy-mm-dd>.jsonl``. Three
``settings.safety.llm_audit_mode`` modes:

  * ``full``       — record prompt + response verbatim
  * ``hash_only``  — record SHA-256 of each side (default)
  * ``off``        — skip entirely

Callers pass already-computed token + latency stats; this module never
re-tokenises, so it stays cheap on the hot path.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir, settings

logger = logging.getLogger("autocsr.safety.llm_audit")

_LOCK = threading.Lock()


def _llm_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "llm_calls"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _mode() -> str:
    seg = (settings().get("safety") or {})
    m = str(seg.get("llm_audit_mode") or "hash_only").lower()
    return m if m in ("full", "hash_only", "off") else "hash_only"


def _h(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _serialise_messages(messages: list[dict[str, Any]]) -> str:
    parts = []
    for m in messages or []:
        role = m.get("role", "")
        c = m.get("content")
        if isinstance(c, list):
            text = " ".join(
                p.get("text", "") for p in c
                if isinstance(p, dict) and "text" in p
            )
        else:
            text = str(c or "")
        parts.append(f"{role}: {text}")
    return "\n".join(parts)


def log_llm_call(
    project_id: str | None,
    *,
    caller_agent: str,
    model: str,
    messages: list[dict[str, Any]] | None = None,
    response_text: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    via: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one LLM call record. ``project_id`` may be ``None`` for
    project-less calls (e.g. /llm/ping); those are dropped quietly."""
    if not project_id:
        return
    mode = _mode()
    if mode == "off":
        return
    prompt_text = _serialise_messages(messages or [])
    resp_text = response_text or ""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "caller_agent": caller_agent,
        "model": model,
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "latency_ms": int(latency_ms),
        "via": via,
        "prompt_hash": _h(prompt_text),
        "response_hash": _h(resp_text),
    }
    if mode == "full":
        # Truncate for sanity — full prompts can be megabytes.
        record["prompt"] = prompt_text[:200_000]
        record["response"] = resp_text[:200_000]
    if extra:
        record["extra"] = extra
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _llm_dir(project_id) / f"{day}.jsonl"
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    try:
        with _LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception as e:  # noqa: BLE001
        logger.warning("llm audit write failed for %s: %s", project_id, e)
