"""BaseAgent wrappers around the writer + harmonizer + chat editor.

These complement (not replace) the existing functions in :mod:`app.report.*`
so the M4/M5 orchestrators keep working unchanged while M6+ orchestrators
can drive them through the uniform AgentInput/AgentOutput surface.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.report.chat_editor import chat_turn
from app.report.harmonizer import harmonize as harmonize_fn
from app.report.writer_agent import WriterContext, write_section
from app.schemas.agent import AgentInput, AgentOutput, LLMMeta
from app.schemas.outline import OutlineNode


class WriterAgent(BaseAgent):
    """Single-section writer. ``payload`` carries ``node`` (OutlineNode dict)
    + optional ``context`` (WriterContext dict)."""

    name = "Writer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        node_raw = payload.get("node")
        if not node_raw:
            raise AgentError("missing payload.node", retryable=False)
        try:
            node = OutlineNode.model_validate(node_raw)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"invalid OutlineNode payload: {e}", retryable=False)
        ctx_raw = payload.get("context") or {}
        ctx = WriterContext(project_id=agent_input.project_id, **{
            k: v for k, v in ctx_raw.items()
            if k in WriterContext.model_fields and k != "project_id"
        })
        try:
            draft = await write_section(agent_input.project_id, node, ctx)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"writer.write_section failed: {e}", cause=e)
        llm_meta = LLMMeta(
            model=draft.llm_meta.model,
            tokens_in=draft.llm_meta.tokens_in,
            tokens_out=draft.llm_meta.tokens_out,
            latency_ms=draft.llm_meta.latency_ms,
            via=draft.llm_meta.via,
        )
        return AgentOutput(
            ok=draft.status != "error",
            result=draft.model_dump(),
            warnings=list(draft.warnings or []),
            llm_meta=llm_meta,
            meta={"node_id": node.id},
        )


class HarmonizerAgent(BaseAgent):
    """Wraps the whole-report harmonizer pass."""

    name = "Harmonizer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        report = payload.get("report")
        outline = payload.get("outline")
        if not report or not outline:
            raise AgentError("missing payload.report or payload.outline",
                              retryable=False)
        try:
            new_report = await harmonize_fn(agent_input.project_id, report, outline)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"harmonizer failed: {e}", cause=e)
        return AgentOutput(
            ok=True,
            result=new_report.model_dump(),
            llm_meta=LLMMeta(
                tokens_in=new_report.total_tokens.input,
                tokens_out=new_report.total_tokens.output,
                via="llm",
            ),
        )


class ChatEditorAgent(BaseAgent):
    """One turn of the conversational section editor."""

    name = "ChatEditor"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        node_id = payload.get("node_id")
        user_message = payload.get("user_message") or payload.get("message")
        history = payload.get("history") or []
        if not (node_id and user_message):
            raise AgentError("missing payload.node_id or payload.user_message",
                              retryable=False)
        try:
            turn = await chat_turn(
                agent_input.project_id, node_id, user_message, history,
            )
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"chat_editor failed: {e}", cause=e)
        meta_obj: Any = turn.assistant_message.meta or {}
        llm_meta = LLMMeta(
            tokens_in=int(meta_obj.get("tokens_in", 0) or 0),
            tokens_out=int(meta_obj.get("tokens_out", 0) or 0),
            via=str(meta_obj.get("llm_via") or ""),
        )
        return AgentOutput(
            ok=True,
            result=turn.model_dump(),
            warnings=list(turn.new_warnings or []),
            llm_meta=llm_meta,
            meta={"node_id": node_id, "new_version": turn.new_version},
        )
