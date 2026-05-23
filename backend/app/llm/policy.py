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

M15 also exports :func:`pii_guard` which inspects every outgoing message
list against the safety scanner. Modes (``settings.safety.pii_pre_check``):
  strict        — raise PIIError on first finding
  auto_redact   — rewrite messages with ``<REDACTED_*>`` markers
  warn          — emit WS event, do nothing else
  off (default) — skip entirely
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("autocsr.llm.policy")


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


# ---------------------------------------------------------------------------
# PII guard (M15)
# ---------------------------------------------------------------------------

def _pii_settings() -> dict[str, Any]:
    try:
        from app.config import settings
        seg = settings().get("safety") or {}
    except Exception:
        seg = {}
    return {
        "pre_check": str(seg.get("pii_pre_check") or "off").lower(),
        "llm_check": bool(seg.get("pii_llm_check") or False),
    }


def pii_guard(
    messages: list[dict[str, Any]],
    *,
    project_id: str | None = None,
    caller: str = "llm",
) -> list[dict[str, Any]]:
    """Apply the configured PII pre-check policy and return the (possibly
    redacted) message list. Raises :class:`PIIError` in strict mode."""
    from app.safety.pii_scanner import PIIError, scan
    from app.safety.redactor import redact

    cfg = _pii_settings()
    mode = cfg["pre_check"]
    if mode == "off":
        return messages
    use_llm = cfg["llm_check"]

    all_findings: list[Any] = []
    needs_rewrite = mode == "auto_redact"
    new_messages: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        c = m.get("content")
        if isinstance(c, list):
            parts: list[dict[str, Any]] = []
            for p in c:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    text = p["text"]
                    found = scan(text, use_llm=use_llm)
                    all_findings.extend(found)
                    if needs_rewrite and found:
                        parts.append({**p, "text": redact(text, found)})
                    else:
                        parts.append(p)
                else:
                    parts.append(p)
            new_messages.append({**m, "content": parts})
        elif isinstance(c, str):
            found = scan(c, use_llm=use_llm)
            all_findings.extend(found)
            if needs_rewrite and found:
                new_messages.append({**m, "content": redact(c, found)})
            else:
                new_messages.append(m)
        else:
            new_messages.append(m)

    if not all_findings:
        return messages

    payload = {
        "findings": [f.to_dict() for f in all_findings[:50]],
        "action": mode, "caller": caller,
    }
    try:
        if project_id:
            from app.server.ws import publish_sync
            publish_sync(project_id, "safety.pii_detected", payload)
    except Exception:
        pass
    logger.warning("pii detected n=%d mode=%s caller=%s",
                   len(all_findings), mode, caller)

    if mode == "strict":
        raise PIIError(
            f"pii pre-check blocked LLM call (n={len(all_findings)})",
            findings=all_findings,
        )
    if mode == "warn":
        return messages
    # auto_redact
    return new_messages
