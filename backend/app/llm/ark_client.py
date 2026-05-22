"""OpenAI-compat / Anthropic-compat LLM client for AutoCSR.

Slimmed from the PPT project's `app/llm/ark_client.py`:
  * keep:  responses() / responses_json() / simple_text() with retry + cost tracking
  * keep:  OpenAI chat/completions AND Anthropic /v1/messages (auto-detected by
           api_format or `/anthropic` in base_url) — DeepSeek users hit both.
  * drop:  vision probes, embedding, chat_with_tools, image-strip helpers, the
           Responses-API <-> Anthropic message converter for tool_use.
           Those return in M2+ when we wire ingestion / writer agents.

Public surface:
    responses(messages, *, timeout, max_tokens, ...) -> {text, raw, via}
    responses_json(messages, schema, ...) -> dict
    simple_text(prompt, *, system=None) -> str
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from typing import Any

import httpx

from app.config import settings
from app.llm import cost_tracker as _ct


_TIMING_ENABLED = os.environ.get("CSR_TIMING", "1") not in ("0", "false", "no")
DEFAULT_OUTPUT_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "16000"))


# Module-level connection pool: TCP+TLS handshake reused across calls.
_GLOBAL_CLIENT = httpx.Client(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    timeout=httpx.Timeout(600.0),
)


def _close_global_client() -> None:
    try:
        _GLOBAL_CLIENT.close()
    except Exception:
        pass


import atexit as _atexit
_atexit.register(_close_global_client)


def _log_timing(tag: str, **fields: Any) -> None:
    if not _TIMING_ENABLED:
        return
    parts = [f"[TIMING][{tag}]"]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    print(" ".join(parts), file=sys.stderr, flush=True)


def _output_max_tokens(max_tokens: int | None = None) -> int:
    return max_tokens if max_tokens is not None else DEFAULT_OUTPUT_MAX_TOKENS


class ArkError(RuntimeError):
    """Wraps any LLM HTTP / parse failure surfaced to the caller."""


# ---------------------------------------------------------------------------
# Configuration accessors
# ---------------------------------------------------------------------------

def _llm_conf() -> tuple[str, str, str, str, str]:
    """Return (base, key, model, user_agent, via) for the chosen LLM segment."""
    seg = settings().get("llm") or {}
    if not seg.get("api_key"):
        raise ArkError("llm.api_key not configured")
    return (
        str(seg.get("base_url", "")).rstrip("/"),
        str(seg["api_key"]),
        str(seg.get("model", "")),
        str(seg.get("user_agent") or ""),
        "llm",
    )


def _llm_api_format() -> str:
    """openai | anthropic — picked from settings.llm.api_format, with auto-detect."""
    seg = settings().get("llm") or {}
    explicit = str(seg.get("api_format") or "").strip().lower()
    if explicit:
        return explicit
    base_url = str(seg.get("base_url") or "").strip().lower().rstrip("/")
    if base_url.endswith("/anthropic") or "/anthropic/" in base_url:
        return "anthropic"
    return "openai"


# ---------------------------------------------------------------------------
# HTTP retry with cost tracking
# ---------------------------------------------------------------------------

def _retrying_post(
    url: str,
    *,
    json_body: dict,
    max_retries: int = 6,
    via: str = "llm",
    headers: dict | None = None,
    timeout: float | httpx.Timeout | None = None,
) -> httpx.Response:
    """Exponential-backoff retry for 429/5xx and transient network errors."""
    delay = 1.5
    last_exc: Exception | None = None
    endpoint = url.rsplit("/", 1)[-1]
    req_bytes = len(json.dumps(json_body, ensure_ascii=False).encode("utf-8"))
    post_kw: dict[str, Any] = {"json": json_body}
    if headers is not None:
        post_kw["headers"] = headers
    if timeout is not None:
        post_kw["timeout"] = timeout

    r: httpx.Response | None = None
    for attempt in range(max_retries):
        t0 = time.time()
        try:
            r = _GLOBAL_CLIENT.post(url, **post_kw)
        except (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            httpx.WriteError,
        ) as e:
            dt = (time.time() - t0) * 1000
            last_exc = e
            _log_timing("LLM_ERR", ep=endpoint, via=via, attempt=attempt,
                        ms=int(dt), err=type(e).__name__)
            if attempt == max_retries - 1:
                raise
            time.sleep(delay + random.random() * 0.5)
            delay *= 2
            continue

        dt = (time.time() - t0) * 1000
        usage_obj = None
        pt = ct = cached = "-"
        try:
            d = r.json()
            u = d.get("usage") or {}
            usage_obj = u
            pt = u.get("prompt_tokens", u.get("input_tokens", "-"))
            ct = u.get("completion_tokens", u.get("output_tokens", "-"))
            ptd = u.get("prompt_tokens_details") or {}
            cached = ptd.get("cached_tokens", u.get("cache_read_input_tokens", "-"))
        except Exception:
            pass

        # Cost tracker is best-effort.
        try:
            if usage_obj and r.status_code < 400:
                _ct.record(endpoint, usage=usage_obj, via=via, latency_ms=int(dt))
        except Exception:
            pass

        if r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
            _log_timing("LLM_RETRY", ep=endpoint, via=via, attempt=attempt,
                        ms=int(dt), status=r.status_code, req_kb=req_bytes // 1024)
            time.sleep(delay + random.random() * 0.5)
            delay *= 2
            continue

        _log_timing("LLM", ep=endpoint, via=via, attempt=attempt, ms=int(dt),
                    status=r.status_code, req_kb=req_bytes // 1024,
                    prompt=pt, completion=ct, cached=cached)
        return r

    if last_exc:
        raise last_exc
    assert r is not None
    return r


# ---------------------------------------------------------------------------
# Message shape conversion (text-only — vision lands in M2+)
# ---------------------------------------------------------------------------

def _to_chat_messages(input_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept either /responses-style ({content: [{type:'input_text'/'text', text}]})
    or plain chat-style ({content: str}) and normalize to chat/completions shape."""
    out: list[dict[str, Any]] = []
    for m in input_messages:
        role = m.get("role", "user")
        c = m.get("content")
        if isinstance(c, str):
            out.append({"role": role, "content": c})
            continue
        if not isinstance(c, list):
            out.append({"role": role, "content": str(c)})
            continue
        # collapse list-of-parts into a single text string
        text_parts: list[str] = []
        for p in c:
            if not isinstance(p, dict):
                continue
            t = p.get("type")
            if t in ("input_text", "text", "output_text") and "text" in p:
                text_parts.append(str(p["text"]))
        out.append({"role": role, "content": "\n".join(text_parts)})
    return out


# ---------------------------------------------------------------------------
# Chat completions (responses)
# ---------------------------------------------------------------------------

def responses(
    messages: list[dict[str, Any]],
    *,
    json_schema: dict | None = None,
    timeout: float = 600.0,
    max_retries: int = 6,
    max_tokens: int | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Single-turn chat. Returns {text, raw, via}.

    Dispatches to OpenAI-compat /chat/completions or Anthropic /v1/messages
    based on settings.llm.api_format (auto-detected from base_url).
    """
    if _llm_api_format() == "anthropic":
        return _responses_anthropic(
            messages, json_schema=json_schema, timeout=timeout,
            max_retries=max_retries, max_tokens=max_tokens,
            temperature=temperature,
        )
    base, key, model, ua, via = _llm_conf()
    chat_messages = _to_chat_messages(messages)

    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": _output_max_tokens(max_tokens),
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if json_schema is not None:
        schema_obj = json_schema.get("schema", json_schema) if isinstance(json_schema, dict) else json_schema
        hint = (
            "\n\nReturn ONLY a single JSON object matching this schema. "
            "No markdown code fences, no prose:\n"
            f"{json.dumps(schema_obj, ensure_ascii=False)}"
        )
        if chat_messages and chat_messages[-1].get("role") == "user":
            chat_messages[-1]["content"] = str(chat_messages[-1]["content"]) + hint
        else:
            chat_messages.append({"role": "user", "content": hint})
        payload["messages"] = chat_messages

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if ua:
        headers["User-Agent"] = ua

    r = _retrying_post(
        f"{base}/chat/completions", json_body=payload,
        max_retries=max_retries, via=via, headers=headers, timeout=timeout,
    )
    if r.status_code >= 400:
        raise ArkError(f"{via} chat/completions HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    return {"text": _extract_chat_text(data), "raw": data, "via": via}


def _extract_chat_text(data: dict) -> str:
    try:
        choices = data.get("choices") or []
        if not choices:
            return json.dumps(data, ensure_ascii=False)
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
            return "".join(parts)
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return json.dumps(data, ensure_ascii=False)


def _responses_anthropic(
    messages: list[dict[str, Any]],
    *,
    json_schema: dict | None = None,
    timeout: float = 600.0,
    max_retries: int = 6,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Minimal text-only adapter for Anthropic /v1/messages."""
    base, key, model, ua, via = _llm_conf()
    sys_text = ""
    a_msgs: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        c = m.get("content")
        if isinstance(c, list):
            text = "\n".join(
                p.get("text", "") for p in c
                if isinstance(p, dict) and "text" in p
            )
        else:
            text = str(c or "")
        if role == "system":
            sys_text = (sys_text + "\n\n" + text) if sys_text else text
            continue
        if not text.strip():
            continue
        a_msgs.append({"role": role, "content": [{"type": "text", "text": text}]})

    if json_schema is not None and a_msgs:
        schema_obj = json_schema.get("schema", json_schema) if isinstance(json_schema, dict) else json_schema
        hint = (
            "\n\nReturn ONLY a single JSON object matching this schema, no markdown, no prose:\n"
            + json.dumps(schema_obj, ensure_ascii=False)
        )
        last = a_msgs[-1]
        if last.get("role") == "user" and isinstance(last.get("content"), list):
            last["content"].append({"type": "text", "text": hint})
        else:
            a_msgs.append({"role": "user", "content": [{"type": "text", "text": hint}]})

    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": _output_max_tokens(max_tokens),
        "messages": a_msgs,
    }
    if sys_text:
        payload["system"] = sys_text
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    if ua:
        headers["User-Agent"] = ua

    r = _retrying_post(
        f"{base}/v1/messages", json_body=payload,
        max_retries=max_retries, via=f"{via}/anthropic",
        headers=headers, timeout=timeout,
    )
    if r.status_code >= 400:
        raise ArkError(f"{via} /v1/messages HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    text_parts = [b.get("text", "") for b in (data.get("content") or []) if b.get("type") == "text"]
    return {"text": "".join(text_parts), "raw": data, "via": via}


# ---------------------------------------------------------------------------
# JSON-output with multi-tier repair
# ---------------------------------------------------------------------------

def responses_json(
    messages: list[dict[str, Any]],
    schema: dict,
    *,
    reasoning_effort: str | None = None,
    **kw: Any,
) -> dict:
    """LLM JSON output with progressive error tolerance.

    Tier 1: strip ```json fences
    Tier 2: extract first { to last }
    Tier 3: heuristic JSON repair (trailing commas, smart quotes)
    Tier 4: one retry with a stronger instruction
    """
    out = responses(messages, json_schema=schema, reasoning_effort=reasoning_effort, **kw)
    text = (out["text"] or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text.lstrip("`")
        if text.rstrip().endswith("```"):
            text = text.rstrip().rstrip("`").rstrip()
    s, e = text.find("{"), text.rfind("}")
    extract = text[s:e + 1] if (s >= 0 and e > s) else text
    try:
        return json.loads(extract)
    except json.JSONDecodeError as je:
        repaired = _repair_json(extract)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
        retry_msgs = list(messages) + [{
            "role": "user",
            "content": (
                f"Your previous reply could not be parsed as JSON "
                f"({je.msg} at line {je.lineno} col {je.colno}). "
                "Reply with ONLY a single valid JSON object that matches the schema. "
                "No markdown, no prose, no trailing commas."
            ),
        }]
        out2 = responses(retry_msgs, json_schema=schema, reasoning_effort=reasoning_effort, **kw)
        text2 = (out2["text"] or "").strip()
        if text2.startswith("```"):
            text2 = text2.split("\n", 1)[1] if "\n" in text2 else text2.lstrip("`")
            if text2.rstrip().endswith("```"):
                text2 = text2.rstrip().rstrip("`").rstrip()
        s2, e2 = text2.find("{"), text2.rfind("}")
        extract2 = text2[s2:e2 + 1] if (s2 >= 0 and e2 > s2) else text2
        try:
            return json.loads(extract2)
        except json.JSONDecodeError:
            return json.loads(_repair_json(extract2))


def _repair_json(text: str) -> str:
    """Best-effort fixes for common LLM JSON mistakes."""
    import re as _re
    text = _re.sub(r"//[^\n]*", "", text)
    text = _re.sub(r"/\*.*?\*/", "", text, flags=_re.DOTALL)
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = _re.sub(r",\s*([}\]])", r"\1", text)
    text = _re.sub(r"(}|])(\s*\n\s*)([\"\[{])", r"\1,\2\3", text)
    return text


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def simple_text(prompt: str, *, system: str | None = None, **kw: Any) -> str:
    """One-shot prompt → text reply."""
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return responses(msgs, **kw)["text"]
