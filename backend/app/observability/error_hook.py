"""Pluggable error-sink registry (M17).

Other plugins (Sentry, Webhook, Datadog) register a callable here and
the BaseAgent / FastAPI exception handlers fan out to every sink. The
default install ships **zero** sinks so the open-source build never
leaks errors to a third party.

Example::

    from app.observability.error_hook import register_error_sink

    def to_sentry(name: str, exc: BaseException, **ctx):
        sentry_sdk.capture_exception(exc, scope=ctx)

    register_error_sink(to_sentry)
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, List

logger = logging.getLogger("autocsr.observability.error_hook")

ErrorSink = Callable[..., None]

_LOCK = threading.RLock()
_SINKS: List[ErrorSink] = []


def register_error_sink(sink: ErrorSink) -> None:
    """Add a sink. Idempotent on identity equality."""
    with _LOCK:
        if sink in _SINKS:
            return
        _SINKS.append(sink)


def unregister_error_sink(sink: ErrorSink) -> bool:
    with _LOCK:
        try:
            _SINKS.remove(sink)
            return True
        except ValueError:
            return False


def get_error_sinks() -> list[ErrorSink]:
    """Return a snapshot of currently registered sinks."""
    with _LOCK:
        return list(_SINKS)


def clear_error_sinks() -> None:
    """Wipe all sinks. Used in unit tests."""
    with _LOCK:
        _SINKS.clear()


def dispatch_error(source: str, exc: BaseException, **context: Any) -> int:
    """Call every registered sink. Returns the number successfully invoked.

    Sink failures are swallowed (and logged) so a misbehaving sink can
    never block the originating mutation.
    """
    sinks = get_error_sinks()
    if not sinks:
        return 0
    count = 0
    for sink in sinks:
        try:
            sink(source, exc, **context)
            count += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("error_sink_failed: %s sink=%s", e, sink)
    return count


__all__ = [
    "register_error_sink", "unregister_error_sink",
    "get_error_sinks", "clear_error_sinks", "dispatch_error",
]
