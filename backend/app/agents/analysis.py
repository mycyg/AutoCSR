"""BaseAgent wrappers around the 4 analysis modules + auto_analyze.

The underlying functions in :mod:`app.analysis` remain canonical; these
agents simply route into them through the AgentInput/AgentOutput envelope
so the orchestrator can collect uniform telemetry.
"""
from __future__ import annotations

import asyncio

from app.agents.base import AgentError, BaseAgent
from app.analysis import descriptive, inferential, safety, survival
from app.analysis.auto import auto_analyze as _auto_analyze
from app.analysis.store import save as save_block
from app.schemas.agent import AgentInput, AgentOutput


class DescriptiveAgent(BaseAgent):
    name = "DescriptiveAnalysis"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        params = agent_input.payload or {}
        try:
            block = await asyncio.to_thread(descriptive.baseline_table, **params)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"descriptive failed: {e}", cause=e, retryable=False)
        saved = await asyncio.to_thread(save_block, agent_input.project_id, block)
        return AgentOutput(ok=True, result=saved.model_dump())


class InferentialAgent(BaseAgent):
    name = "InferentialAnalysis"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        params = agent_input.payload or {}
        try:
            block = await asyncio.to_thread(inferential.compare_groups, **params)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"inferential failed: {e}", cause=e, retryable=False)
        saved = await asyncio.to_thread(save_block, agent_input.project_id, block)
        return AgentOutput(ok=True, result=saved.model_dump())


class SurvivalAgent(BaseAgent):
    name = "SurvivalAnalysis"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        params = dict(agent_input.payload or {})
        sub = (params.pop("subtype", None) or "km").lower()
        try:
            if sub == "cox":
                block = await asyncio.to_thread(survival.cox_regression, **params)
            else:
                block = await asyncio.to_thread(survival.km_estimate, **params)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"survival failed: {e}", cause=e, retryable=False)
        saved = await asyncio.to_thread(save_block, agent_input.project_id, block)
        return AgentOutput(ok=True, result=saved.model_dump(),
                            meta={"subtype": sub})


class SafetyAgent(BaseAgent):
    name = "SafetyAnalysis"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        params = agent_input.payload or {}
        try:
            block = await asyncio.to_thread(safety.ae_summary, **params)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"safety failed: {e}", cause=e, retryable=False)
        saved = await asyncio.to_thread(save_block, agent_input.project_id, block)
        return AgentOutput(ok=True, result=saved.model_dump())


class AutoAnalysisAgent(BaseAgent):
    """Convenience wrapper around :func:`app.analysis.auto.auto_analyze`."""

    name = "AutoAnalysis"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        try:
            blocks = await asyncio.to_thread(_auto_analyze, agent_input.project_id)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"auto_analyze failed: {e}", cause=e)
        return AgentOutput(
            ok=True,
            result={"ids": [b.id for b in blocks], "n_blocks": len(blocks)},
        )
