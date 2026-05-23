"""Medical English polishing agent (M20 v2.2).

Three modes:
  academic   — rigorous, formal, dense; promotes nominalisation, citation density
  concise    — strip filler, keep core data; ≤90 % of source length
  formal     — neutral / journal-ready; defuse colloquialisms

The agent **must not** alter scientific conclusions or data values. It
returns a unified diff so the user can review and accept selectively.

Mock mode (CSR_POLISH_MOCK=1 or CSR_WRITER_MOCK=1) bypasses the LLM and
produces a deterministic polish: trims whitespace, swaps a handful of
filler words, and prepends ``> [polished:<mode>] `` to the first paragraph.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentError, BaseAgent
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses
from app.observability.logger import get_logger
from app.schemas.agent import AgentInput, AgentOutput, LLMMeta

logger = get_logger("Polisher")

PolishMode = Literal["academic", "concise", "formal"]


class PolishInput(BaseModel):
    markdown: str
    mode: PolishMode = "academic"
    project_id: str = ""
    node_id: str | None = None


class PolishOutput(BaseModel):
    mode: PolishMode
    original_markdown: str
    polished_markdown: str
    diff: str
    diff_added: int = 0
    diff_removed: int = 0
    llm_meta: LLMMeta = Field(default_factory=LLMMeta)


_SYSTEM_PROMPT_BASE = """You are a senior medical editor for clinical study reports.
Your job is to polish the user-supplied markdown without changing any
scientific data, numbers, citations, or conclusions.

Hard rules:
- NEVER invent or remove data points, percentages, p-values, CIs, references.
- NEVER add a new claim. NEVER soften or strengthen a finding.
- Preserve markdown structure (headings, lists, tables, citation tokens
  like Ref<...>).
- Output ONLY the polished markdown — no commentary, no JSON wrapper.
"""

_MODE_INSTRUCTIONS: dict[PolishMode, str] = {
    "academic": (
        "Style: rigorous academic English. Prefer the passive voice for "
        "methods, third person, precise nominalisations. Expand contractions. "
        "Use field-standard terminology (e.g. 'adverse event' not 'side effect'). "
        "Length target: ±10% of source."
    ),
    "concise": (
        "Style: strip filler words, redundant qualifiers and throat-clearing "
        "openers. Combine short sentences when factual. Length target: 80-90% "
        "of source length. Tables/lists untouched."
    ),
    "formal": (
        "Style: neutral, journal-ready tone. Remove colloquialisms and any "
        "promotional language. Keep sentence rhythm comfortable. Length "
        "target: ±5% of source."
    ),
}


def _is_mock() -> bool:
    return (os.environ.get("CSR_POLISH_MOCK", "").lower() in ("1", "true", "yes")
            or os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")
            or os.environ.get("CSR_EDITOR_MOCK", "").lower() in ("1", "true", "yes"))


_FILLER_PAIRS = [
    (r"\bin order to\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bat the present time\b", "now"),
    (r"\bin spite of the fact that\b", "although"),
    (r"\ba number of\b", "several"),
    (r"\bvery (\w+)\b", r"\1"),
    (r"\bit is important to note that\b", ""),
    (r"\bbasically\b", ""),
    (r"\bactually\b", ""),
]


def _mock_polish(markdown: str, mode: PolishMode) -> str:
    text = markdown
    for pat, repl in _FILLER_PAIRS:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    # Collapse 3+ blank lines and trim trailing whitespace per line
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    banner = f"> [polished:{mode}]\n\n"
    return banner + text.strip() + "\n"


def _build_diff(original: str, polished: str, *, label_a: str = "original",
                  label_b: str = "polished") -> tuple[str, int, int]:
    a_lines = original.splitlines(keepends=True)
    b_lines = polished.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        a_lines, b_lines, fromfile=label_a, tofile=label_b, n=3,
    ))
    added = sum(1 for line in diff_lines
                 if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines
                   if line.startswith("-") and not line.startswith("---"))
    return ("".join(diff_lines), added, removed)


def _call_llm(markdown: str, mode: PolishMode) -> tuple[str, LLMMeta]:
    policy = _policy.editor_llm()
    sys_prompt = _SYSTEM_PROMPT_BASE + "\n\n" + _MODE_INSTRUCTIONS[mode]
    user_msg = (
        "Polish the following markdown per the rules + style above. "
        "Return only the polished markdown.\n\n```markdown\n" + markdown +
        "\n```"
    )
    t0 = time.time()
    try:
        out = llm_responses(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            timeout=policy.timeout,
            max_tokens=policy.max_tokens,
            temperature=policy.temperature,
            reasoning_effort=policy.reasoning_effort,
            caller_agent="polisher",
        )
        text = str((out or {}).get("text") or "")
    except ArkError as e:
        raise AgentError(f"LLM call failed: {e}", retryable=True, cause=e)
    latency_ms = int((time.time() - t0) * 1000)
    # Strip any markdown code fence the LLM wrapped around its output
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown)?\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text.strip() + "\n", LLMMeta(
        model=policy.name, latency_ms=latency_ms, via="llm",
    )


class PolishingAgent(BaseAgent):
    """Polish a markdown blob without altering scientific content."""

    name = "Polisher"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        try:
            payload = PolishInput.model_validate({
                **(agent_input.payload or {}),
                "project_id": agent_input.project_id,
            })
        except Exception as e:        # noqa: BLE001
            raise AgentError(f"invalid PolishInput: {e}", retryable=False)
        original = (payload.markdown or "").strip()
        if not original:
            raise AgentError("markdown is required", retryable=False)

        if _is_mock():
            polished = _mock_polish(original, payload.mode)
            meta = LLMMeta(model="mock", via="mock")
        else:
            try:
                polished, meta = await asyncio.to_thread(
                    _call_llm, original, payload.mode,
                )
            except AgentError:
                # Fallback to mock so the workflow keeps moving
                polished = _mock_polish(original, payload.mode)
                meta = LLMMeta(model="fallback", via="fallback")

        diff, added, removed = _build_diff(original, polished)
        out = PolishOutput(
            mode=payload.mode,
            original_markdown=original,
            polished_markdown=polished,
            diff=diff,
            diff_added=added,
            diff_removed=removed,
            llm_meta=meta,
        )
        return AgentOutput(
            ok=True,
            result=json.loads(out.model_dump_json()),
            llm_meta=meta,
            meta={"mode": payload.mode, "node_id": payload.node_id or ""},
        )


async def polish(markdown: str, *, mode: PolishMode = "academic",
                  project_id: str = "", node_id: str | None = None
                  ) -> PolishOutput:
    """Convenience callable returning a PolishOutput."""
    agent = PolishingAgent()
    inp = AgentInput(
        project_id=project_id,
        payload={
            "markdown": markdown,
            "mode": mode,
            "node_id": node_id,
        },
        meta={"caller": "polish()"},
    )
    out = await agent.run(inp)
    return PolishOutput.model_validate(out.result)


__all__ = ["PolishingAgent", "PolishInput", "PolishOutput", "polish"]
