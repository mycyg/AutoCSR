"""LLM call-policy table for AutoCSR.

Four tiers map to AutoCSR's pipeline phases:
  outline_llm  -> outline_builder (one shot, json_schema)
  writer_llm   -> chapter writers (many parallel, longest, prose-heavy)
  editor_llm   -> chat-editor patches (interactive, low latency wins)
  analyst_llm  -> analysis/* statistical narrative (mid latency, json_schema)

Each call site does:
    from app.llm.policy import for_role
    p = for_role("writer")
    out = responses(messages, timeout=p.timeout, max_tokens=p.max_tokens, ...)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMPolicy:
    name: str
    timeout: float
    max_tokens: int
    temperature: float
    reasoning_effort: str            # "minimal" | "low" | "medium" | "high"
    json_schema: bool                # whether to request structured output


DEFAULT = LLMPolicy(
    name="default", timeout=600.0, max_tokens=8000,
    temperature=0.4, reasoning_effort="medium", json_schema=False,
)


_TABLE: dict[str, LLMPolicy] = {
    "outline": LLMPolicy(
        name="outline_llm", timeout=240.0, max_tokens=16000,
        temperature=0.2, reasoning_effort="medium", json_schema=True,
    ),
    "writer": LLMPolicy(
        name="writer_llm", timeout=480.0, max_tokens=32000,
        temperature=0.4, reasoning_effort="medium", json_schema=False,
    ),
    "editor": LLMPolicy(
        name="editor_llm", timeout=180.0, max_tokens=12000,
        temperature=0.3, reasoning_effort="low", json_schema=False,
    ),
    "analyst": LLMPolicy(
        name="analyst_llm", timeout=180.0, max_tokens=8000,
        temperature=0.1, reasoning_effort="medium", json_schema=True,
    ),
    # generic ping
    "ping": LLMPolicy(
        name="ping", timeout=60.0, max_tokens=128,
        temperature=0.3, reasoning_effort="minimal", json_schema=False,
    ),
}


def for_role(role: str) -> LLMPolicy:
    return _TABLE.get(role, DEFAULT)


def outline_llm() -> LLMPolicy: return for_role("outline")
def writer_llm() -> LLMPolicy:  return for_role("writer")
def editor_llm() -> LLMPolicy:  return for_role("editor")
def analyst_llm() -> LLMPolicy: return for_role("analyst")
