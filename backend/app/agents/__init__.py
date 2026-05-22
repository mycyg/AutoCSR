"""Agent abstraction.

All long-running, LLM-using, or domain-specific actors (ingest workers,
analysis modules, writer, harmonizer, chat editor, sandbox runner) inherit
:class:`BaseAgent` so they share:

  * a uniform ``run(input) -> output`` async signature
  * structured logging (agent.start / agent.done / agent.error)
  * retry-with-backoff on transient errors
  * a typed exception surface (:class:`AgentError`)

Existing modules keep their public helper functions; the BaseAgent
subclasses are thin wrappers that call into those helpers.
"""
from app.agents.base import (
    AgentError,
    BaseAgent,
    retry_on_agent_error,
)
from app.agents.ingestion import IngestWorkerAgent
from app.agents.analysis import (
    AutoAnalysisAgent,
    DescriptiveAgent,
    InferentialAgent,
    SafetyAgent,
    SurvivalAgent,
)
from app.agents.writer import ChatEditorAgent, HarmonizerAgent, WriterAgent

__all__ = [
    "AgentError",
    "BaseAgent",
    "retry_on_agent_error",
    "IngestWorkerAgent",
    "DescriptiveAgent",
    "InferentialAgent",
    "SurvivalAgent",
    "SafetyAgent",
    "AutoAnalysisAgent",
    "WriterAgent",
    "HarmonizerAgent",
    "ChatEditorAgent",
]
