"""Structured JSON logger for AutoCSR agents + pipelines.

Goals:
  - Every agent run emits ``agent.start`` / ``agent.done`` / ``agent.error``
    JSON events with consistent keys (agent_name, project_id, latency_ms,
    tokens_in, tokens_out).
  - Plain text loggers (stdlib ``logging``) keep working; we install a
    structlog processor chain that also routes back into stdlib so uvicorn
    captures every line.
  - Idempotent ``configure_logging`` — safe to call from each entrypoint.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:  # pragma: no cover — fallback path
    structlog = None  # type: ignore[assignment]
    _HAS_STRUCTLOG = False


_CONFIGURED = False
_LOCK = threading.RLock()


def _configure_structlog() -> None:
    """Install the JSON-rendering structlog pipeline.

    Safe to call multiple times. Honors the LOG_LEVEL env var.
    """
    if not _HAS_STRUCTLOG:
        return
    # Default to WARNING so noisy agent.* events do not flood pipes when a
    # parent process captures stderr without draining (m4/m5 test pattern).
    # Set LOG_LEVEL=INFO to see agent events.
    level_name = os.environ.get("LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    # Plain stdlib root so uvicorn / fastapi loggers still work
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    root.setLevel(level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def configure_logging() -> None:
    """Idempotent global setup. Call from server startup + tests + scripts."""
    global _CONFIGURED
    with _LOCK:
        if _CONFIGURED:
            return
        _configure_structlog()
        _CONFIGURED = True


class _StdlibAdapter:
    """Light wrapper that mimics structlog's BoundLogger API on top of stdlib
    logging — used when structlog isn't installed."""

    def __init__(self, name: str, context: dict[str, Any] | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._context = dict(context or {})

    def bind(self, **kwargs: Any) -> "_StdlibAdapter":
        new = _StdlibAdapter(self._logger.name, {**self._context, **kwargs})
        return new

    def _emit(self, level: int, event: str, **kwargs: Any) -> None:
        merged = {**self._context, **kwargs, "event": event}
        # Keep the line readable
        kv = " ".join(f"{k}={v}" for k, v in merged.items() if k != "event")
        self._logger.log(level, "%s %s", event, kv) if kv else self._logger.log(level, "%s", event)

    def debug(self, event: str, **kwargs: Any) -> None: self._emit(logging.DEBUG, event, **kwargs)
    def info(self, event: str, **kwargs: Any) -> None: self._emit(logging.INFO, event, **kwargs)
    def warning(self, event: str, **kwargs: Any) -> None: self._emit(logging.WARNING, event, **kwargs)
    def error(self, event: str, **kwargs: Any) -> None: self._emit(logging.ERROR, event, **kwargs)
    def exception(self, event: str, **kwargs: Any) -> None:
        self._logger.exception("%s %s", event, kwargs)


def get_logger(name: str, **initial_context: Any) -> Any:
    """Return a bound structured logger.

    When structlog is installed the return value is a structlog BoundLogger;
    otherwise a stdlib-backed shim with the same .bind/.info/.error surface.
    """
    configure_logging()
    if _HAS_STRUCTLOG:
        log = structlog.get_logger(name)
        if initial_context:
            log = log.bind(**initial_context)
        return log
    return _StdlibAdapter(name, initial_context)
