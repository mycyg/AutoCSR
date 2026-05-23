"""Prometheus metrics surface (M17).

Exposes ``/metrics`` in Prometheus text format. We optionally use the
``prometheus_client`` package — if it is unavailable we still expose
the endpoint with a friendly note so the route map stays stable.

Five core series:

* ``csr_agent_runs_total{agent,status}``     Counter
* ``csr_agent_duration_seconds{agent}``      Histogram
* ``csr_llm_tokens_total{model,direction}``  Counter
* ``csr_queue_depth{kind}``                  Gauge
* ``csr_active_projects``                    Gauge

The Counter / Histogram helpers below are no-ops when the package is
missing so call sites stay one-liners.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

logger = logging.getLogger("autocsr.observability.metrics")


router = APIRouter(tags=["observability"])


# ---------------------------------------------------------------------------
# Best-effort prometheus_client import
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (  # type: ignore[import-not-found]
        CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram,
        generate_latest,
    )
    _HAS_PROM = True
    _REG = CollectorRegistry()

    AGENT_RUNS = Counter(
        "csr_agent_runs_total",
        "Total agent.run invocations by name and outcome.",
        ["agent", "status"],
        registry=_REG,
    )
    AGENT_DURATION = Histogram(
        "csr_agent_duration_seconds",
        "agent.run latency in seconds.",
        ["agent"],
        registry=_REG,
        buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0),
    )
    LLM_TOKENS = Counter(
        "csr_llm_tokens_total",
        "LLM tokens by model and direction (in/out).",
        ["model", "direction"],
        registry=_REG,
    )
    QUEUE_DEPTH = Gauge(
        "csr_queue_depth",
        "Pending jobs per queue kind.",
        ["kind"],
        registry=_REG,
    )
    ACTIVE_PROJECTS = Gauge(
        "csr_active_projects",
        "Number of projects currently being mutated.",
        registry=_REG,
    )
except Exception as e:  # noqa: BLE001
    logger.info("prometheus_client unavailable; /metrics will return a stub: %s", e)
    _HAS_PROM = False
    _REG = None  # type: ignore[assignment]
    AGENT_RUNS = AGENT_DURATION = LLM_TOKENS = QUEUE_DEPTH = ACTIVE_PROJECTS = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


# ---------------------------------------------------------------------------
# Public helpers (no-ops when prometheus_client absent)
# ---------------------------------------------------------------------------

def inc_agent_run(agent: str, status: str) -> None:
    if not _HAS_PROM:
        return
    try:
        AGENT_RUNS.labels(agent=agent, status=status).inc()
    except Exception:
        pass


def observe_agent_duration(agent: str, seconds: float) -> None:
    if not _HAS_PROM:
        return
    try:
        AGENT_DURATION.labels(agent=agent).observe(max(0.0, float(seconds)))
    except Exception:
        pass


def add_llm_tokens(model: str, direction: str, n: int) -> None:
    if not _HAS_PROM or n <= 0:
        return
    try:
        LLM_TOKENS.labels(model=model or "unknown",
                          direction=direction or "out").inc(int(n))
    except Exception:
        pass


def set_queue_depth(kind: str, depth: int) -> None:
    if not _HAS_PROM:
        return
    try:
        QUEUE_DEPTH.labels(kind=kind).set(max(0, int(depth)))
    except Exception:
        pass


def inc_active_projects(delta: int = 1) -> None:
    if not _HAS_PROM:
        return
    try:
        ACTIVE_PROJECTS.inc(delta)
    except Exception:
        pass


@contextmanager
def time_agent(agent: str) -> Iterator[None]:
    """Context manager: time a block + emit count + duration."""
    t0 = time.time()
    inc_active_projects(1)
    status = "ok"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        inc_active_projects(-1)
        observe_agent_duration(agent, time.time() - t0)
        inc_agent_run(agent, status)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/metrics")
def metrics_endpoint() -> Response:
    if not _HAS_PROM:
        return PlainTextResponse(
            "# prometheus_client not installed — pip install prometheus_client\n",
            media_type="text/plain; charset=utf-8",
            status_code=503,
        )
    body = generate_latest(_REG)
    return Response(body, media_type=CONTENT_TYPE_LATEST)


__all__ = [
    "router", "inc_agent_run", "observe_agent_duration", "add_llm_tokens",
    "set_queue_depth", "inc_active_projects", "time_agent",
]
