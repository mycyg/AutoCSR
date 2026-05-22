"""Schemas for the BaseAgent contract.

These types are shared by every agent (ingest worker, analysis, writer,
harmonizer, chat editor, sandbox runner). Each agent's input / output extends
:class:`AgentInput` / :class:`AgentOutput` with a typed ``payload`` block; the
``meta`` dict on each side is reserved for orchestrators (project_id,
parent_node_id, trace_id, etc.).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMMeta(BaseModel):
    """Cost / latency record for one LLM call.

    Compatible with :class:`app.schemas.report.LLMMeta` — we keep this schema
    in sync but expose it here so non-report agents can use the same shape
    without importing report-specific types.
    """
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cost: float | None = None
    via: str = ""           # "llm" / "mock" / "fallback"


class AgentInput(BaseModel):
    """Generic input envelope for any :class:`BaseAgent`.

    Concrete agents read agent-specific fields out of ``payload`` and may
    populate ``meta`` (project_id, file_id, etc.) for logging.
    """
    project_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Generic output envelope.

    Concrete agents stuff their result into ``result`` (Pydantic model
    serialized via ``model_dump`` or a raw dict). ``warnings`` lets the
    orchestrator inspect non-fatal anomalies; ``llm_meta`` is set when the
    agent used a LLM.
    """
    ok: bool = True
    result: Any = None
    warnings: list[str] = Field(default_factory=list)
    llm_meta: LLMMeta | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
