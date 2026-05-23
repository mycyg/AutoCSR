"""Unit tests for BaseAgent + AgentError + retry decorator (M17)."""
from __future__ import annotations

import asyncio

import pytest

from app.agents.base import AgentError, BaseAgent, retry_on_agent_error
from app.schemas.agent import AgentInput, AgentOutput


class _OkAgent(BaseAgent):
    name = "OkAgent"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        return AgentOutput(ok=True, result={"echo": agent_input.payload})


class _FlakyAgent(BaseAgent):
    name = "FlakyAgent"

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        self.attempts += 1
        if self.attempts < 3:
            raise AgentError("flaky", retryable=True)
        return AgentOutput(ok=True, result={"attempts": self.attempts})


class _BadAgent(BaseAgent):
    name = "BadAgent"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        raise ValueError("programming error")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_baseagent_runs_and_returns_output():
    agent = _OkAgent()
    out = _run(agent.run(AgentInput(project_id="p1", payload={"x": 1})))
    assert out.ok is True
    assert out.result == {"echo": {"x": 1}}


def test_baseagent_propagates_value_error_immediately():
    agent = _BadAgent()
    with pytest.raises(ValueError):
        _run(agent.run(AgentInput(project_id="p2")))


def test_agent_error_carries_retryable_flag():
    e = AgentError("nope", retryable=False)
    assert e.retryable is False
    e2 = AgentError("retry me")
    assert e2.retryable is True


def test_retry_decorator_succeeds_after_two_failures():
    flaky = _FlakyAgent()

    @retry_on_agent_error(max_attempts=4, backoff=0.0)
    async def _doit():
        return await flaky.run(AgentInput(project_id="p3"))

    out = _run(_doit())
    assert out.ok is True
    assert flaky.attempts == 3


def test_retry_decorator_gives_up_after_max_attempts():
    class _Always(BaseAgent):
        name = "Always"

        async def _run(self, agent_input):  # noqa: ANN001
            raise AgentError("nope")

    agent = _Always()

    @retry_on_agent_error(max_attempts=2, backoff=0.0)
    async def _doit():
        return await agent.run(AgentInput(project_id="p4"))

    with pytest.raises(AgentError):
        _run(_doit())
