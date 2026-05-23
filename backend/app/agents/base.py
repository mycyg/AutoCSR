"""BaseAgent abstraction + AgentError + retry decorator.

Design notes
------------

* ``BaseAgent.run(...)`` is the public, instrumented entrypoint that emits
  ``agent.start`` / ``agent.done`` / ``agent.error`` JSON events. Subclasses
  override ``_run(input)`` which carries the actual work.

* ``retry_on_agent_error(max_attempts, backoff)`` decorates any async callable
  and re-invokes it on :class:`AgentError`. Each retry doubles the backoff up
  to a small ceiling so tests stay fast.

* The base class does NOT manage transactions or persistence — each subclass
  remains responsible for saving its own artefacts (parquet, snapshot, etc.).
  This keeps the abstraction thin enough that existing modules can adopt it
  without behavioural changes.
"""
from __future__ import annotations

import abc
import asyncio
import functools
import time
from typing import Any, Callable, Coroutine, TypeVar

from app.observability.logger import get_logger
from app.schemas.agent import AgentInput, AgentOutput


class AgentError(Exception):
    """Recoverable agent failure.

    Subclasses (or callers) raise this when an LLM call, parser, or external
    tool fails in a way that a retry might fix. Programming errors should
    still be raised as ``ValueError`` / ``TypeError`` / etc. so they surface
    immediately.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None,
                 retryable: bool = True) -> None:
        super().__init__(message)
        self.cause = cause
        self.retryable = retryable


F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def retry_on_agent_error(max_attempts: int = 3, backoff: float = 1.5,
                          max_backoff: float = 8.0) -> Callable[[F], F]:
    """Async retry decorator.

    Retries only on :class:`AgentError` with ``retryable=True``. Other
    exceptions (ValueError, KeyError, etc.) propagate immediately.
    """
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            delay = max(0.0, float(backoff))
            last: AgentError | None = None
            while True:
                attempt += 1
                try:
                    return await fn(*args, **kwargs)
                except AgentError as e:
                    last = e
                    if not e.retryable or attempt >= max_attempts:
                        raise
                    await asyncio.sleep(min(delay, max_backoff))
                    delay = min(delay * 2 if delay > 0 else 1.0, max_backoff)
            # unreachable
            raise last  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return deco


class BaseAgent(abc.ABC):
    """Abstract base for every AutoCSR agent.

    Subclasses override :meth:`_run`. The public :meth:`run` wraps it with
    structured logging + a fast-path "skip when input invalid" check.
    """

    #: Stable name used in logs; defaults to the class name. Override per
    #: subclass to keep log keys deterministic across renames.
    name: str = ""

    def __init__(self) -> None:
        self.name = self.name or type(self).__name__
        self.logger = get_logger(self.name)

    @abc.abstractmethod
    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        """Subclass entrypoint — return an AgentOutput."""

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """Instrumented public entrypoint.

        Emits agent.start / agent.done / agent.error events with project_id
        and any meta keys carried on the input.
        """
        pid = getattr(agent_input, "project_id", "") or ""
        log = self.logger.bind(agent=self.name, project_id=pid,
                               **{k: v for k, v in (agent_input.meta or {}).items()
                                  if isinstance(v, (str, int, float, bool))})
        log.info("agent.start")
        # M17 — Prometheus + error sinks. Both are optional / no-op when
        # the corresponding modules are missing or misconfigured so the
        # agent contract is unchanged.
        try:
            from app.observability.metrics import (
                add_llm_tokens, inc_active_projects,
                inc_agent_run, observe_agent_duration,
            )
        except Exception:
            add_llm_tokens = inc_active_projects = None  # type: ignore[assignment]
            inc_agent_run = observe_agent_duration = None  # type: ignore[assignment]
        if inc_active_projects is not None:
            inc_active_projects(1)
        t0 = time.time()
        try:
            out = await self._run(agent_input)
        except AgentError as e:
            elapsed = int((time.time() - t0) * 1000)
            log.error("agent.error", error=str(e), kind=type(e).__name__,
                      retryable=getattr(e, "retryable", False), latency_ms=elapsed)
            if observe_agent_duration is not None:
                observe_agent_duration(self.name, elapsed / 1000.0)
                inc_agent_run(self.name, "error")
                inc_active_projects(-1)
            try:
                from app.observability.error_hook import dispatch_error
                dispatch_error(self.name, e, project_id=pid)
            except Exception:
                pass
            raise
        except Exception as e:  # noqa: BLE001
            elapsed = int((time.time() - t0) * 1000)
            log.error("agent.error", error=str(e), kind=type(e).__name__,
                      retryable=False, latency_ms=elapsed)
            if observe_agent_duration is not None:
                observe_agent_duration(self.name, elapsed / 1000.0)
                inc_agent_run(self.name, "error")
                inc_active_projects(-1)
            try:
                from app.observability.error_hook import dispatch_error
                dispatch_error(self.name, e, project_id=pid)
            except Exception:
                pass
            raise
        elapsed = int((time.time() - t0) * 1000)
        if observe_agent_duration is not None:
            observe_agent_duration(self.name, elapsed / 1000.0)
            inc_agent_run(self.name, "ok" if out.ok else "warn")
            inc_active_projects(-1)
        if add_llm_tokens is not None and out.llm_meta:
            add_llm_tokens(out.llm_meta.model or "unknown", "in", out.llm_meta.tokens_in)
            add_llm_tokens(out.llm_meta.model or "unknown", "out", out.llm_meta.tokens_out)
        log_kwargs: dict[str, Any] = {"latency_ms": elapsed, "ok": out.ok,
                                       "n_warnings": len(out.warnings)}
        if out.llm_meta:
            log_kwargs["tokens_in"] = out.llm_meta.tokens_in
            log_kwargs["tokens_out"] = out.llm_meta.tokens_out
            log_kwargs["llm_via"] = out.llm_meta.via
        log.info("agent.done", **log_kwargs)
        return out
