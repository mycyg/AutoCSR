"""Generic LLM ↔ tool action loop (M9 foundation).

The loop is deliberately model-agnostic: it speaks the same JSON action
protocol the M5 chat editor introduced. On every turn the LLM is asked to
emit:

    {
      "actions": [
        {"tool": "<tool_name>", "args": {...}},
        ...
      ]
    }

We execute each action against the registered :class:`ToolSpec` table and
feed the results back as a synthetic ``user`` message. When the LLM emits
``{"tool": "respond", "args": {...}}`` we stop and return.

Hard limits keep things safe:

  * ``max_turns`` (default 5): cap LLM-tool round trips.
  * ``token_budget`` (optional): cumulative ``tokens_in + tokens_out`` across
    turns; exceeding it forces termination with ``terminated='budget'``.
  * Each turn's LLM call goes through ``responses_json`` with the canonical
    action-list schema so malformed output triggers JSON repair / retry
    before we hit the bash-out path.

The loop is asynchronous because every tool handler is async, even when its
body is sync (we wrap sync ones at registration time).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable

from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses, responses_json as llm_responses_json
from app.observability.logger import get_logger
from app.schemas.agent import LLMMeta


logger = get_logger("ToolLoop")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """Shared state every handler can read.

    Tools can stash side-channel state in ``extra`` (e.g. last sandbox
    run_id) so subsequent turns can chain.
    """
    project_id: str = ""
    node_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: Any
    duration_ms: int
    error: str | None = None
    turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "args": self.args,
            "result": _truncate_for_log(self.result),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "turn": self.turn,
        }


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any], ToolContext], Awaitable[Any]]


@dataclass
class ToolLoopResult:
    final_response: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_meta: LLMMeta = field(default_factory=LLMMeta)
    terminated: str = "respond"      # respond | max_turns | budget | error | invalid
    error: str | None = None


# ---------------------------------------------------------------------------
# Action-list JSON schema
# ---------------------------------------------------------------------------

_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                },
                "required": ["tool"],
            },
        },
    },
    "required": ["actions"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate_for_log(value: Any, max_chars: int = 500) -> Any:
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = str(value)
    if len(s) > max_chars:
        return s[:max_chars] + "…(truncated)"
    return value


def _describe_tools(tools: list[ToolSpec]) -> str:
    lines: list[str] = []
    for t in tools:
        schema_dump = json.dumps(t.input_schema, ensure_ascii=False)
        lines.append(f"- `{t.name}` — {t.description}\n  input_schema: {schema_dump}")
    return "\n".join(lines)


def _build_system_prompt(base_system: str, tools: list[ToolSpec]) -> str:
    tool_desc = _describe_tools(tools)
    return (
        f"{base_system.rstrip()}\n\n"
        "## 可用工具\n"
        "每个工具调用都要遵循 input_schema，参数 JSON 必须合法。\n"
        f"{tool_desc}\n\n"
        "## 输出格式\n"
        "你 **只** 能回复一个 JSON 对象 `{\"actions\": [...]}`：\n"
        "- 每个元素 `{\"tool\": <name>, \"args\": <object>}`\n"
        "- 想要结束本轮，调用 `respond` 工具并把最终 markdown 放进 args.markdown\n"
        "- 一次最多写 3 个 actions；遇到不确定的事就调用工具去查，不要在 respond 里凭空回答\n"
        "- 严禁输出 ```json``` 围栏，严禁多余解释\n"
    )


def _serialize_tool_result(name: str, result: Any, error: str | None) -> str:
    """Turn a tool result into a compact text snippet for the next user msg."""
    if error:
        return f"[tool:{name}] ERROR: {error}"
    try:
        body = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        body = str(result)
    if len(body) > 6000:
        body = body[:6000] + "…(truncated)"
    return f"[tool:{name}] OK: {body}"


def _is_mock() -> bool:
    return os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def run_tool_loop(
    *,
    system_prompt: str,
    user_messages: list[dict[str, Any]],
    tools: list[ToolSpec],
    ctx: ToolContext,
    llm_policy: _policy.LLMPolicy | None = None,
    max_turns: int = 5,
    token_budget: int | None = None,
    on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
) -> ToolLoopResult:
    """Drive the LLM ↔ tool loop until ``respond`` or a guard fires."""
    policy = llm_policy or _policy.writer_llm()
    tool_map = {t.name: t for t in tools}
    if "respond" not in tool_map:
        raise ValueError("tool_loop requires a 'respond' tool")

    full_system = _build_system_prompt(system_prompt, tools)
    messages: list[dict[str, Any]] = [{"role": "system", "content": full_system}]
    messages.extend(user_messages)

    tool_calls: list[ToolCall] = []
    total_meta = LLMMeta(model=policy.name, via="llm")
    final_response = ""
    citations: list[dict[str, Any]] = []
    terminated = "max_turns"
    error: str | None = None

    async def _emit(kind: str, payload: dict[str, Any]) -> None:
        if on_event is None:
            return
        try:
            await on_event(kind, payload)
        except Exception:
            pass

    for turn in range(1, max_turns + 1):
        await _emit("turn_start", {"turn": turn})
        # ---- 1. LLM call ----------------------------------------------------
        try:
            import asyncio

            def _go() -> dict[str, Any]:
                return llm_responses_json(
                    messages,
                    _ACTION_SCHEMA,
                    timeout=policy.timeout,
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                    reasoning_effort=policy.reasoning_effort,
                )

            t0 = time.time()
            parsed = await asyncio.to_thread(_go)
            llm_ms = int((time.time() - t0) * 1000)
            total_meta.latency_ms += llm_ms
        except (ArkError, Exception) as e:  # noqa: BLE001
            logger.warning("tool_loop.llm_error", turn=turn, error=str(e)[:200])
            terminated = "error"
            error = f"llm_error:{type(e).__name__}:{str(e)[:200]}"
            break

        actions = (parsed or {}).get("actions")
        if not isinstance(actions, list) or not actions:
            terminated = "invalid"
            error = "LLM did not return a valid actions list"
            break

        # ---- 2. Execute each action ---------------------------------------
        respond_seen = False
        for raw_action in actions[:3]:
            if not isinstance(raw_action, dict):
                continue
            name = str(raw_action.get("tool") or "").strip()
            args = raw_action.get("args") or {}
            if not isinstance(args, dict):
                args = {}
            spec = tool_map.get(name)
            await _emit("tool_call_start", {"turn": turn, "name": name, "args": _truncate_for_log(args)})
            if spec is None:
                # Unknown tool — surface as error tool call, keep going
                tc = ToolCall(name=name, args=args, result=None,
                              duration_ms=0, error="unknown_tool", turn=turn)
                tool_calls.append(tc)
                await _emit("tool_call_error", {"turn": turn, "name": name, "msg": "unknown_tool"})
                messages.append({"role": "user",
                                  "content": _serialize_tool_result(name, None, "unknown_tool")})
                continue

            t1 = time.time()
            try:
                result = await spec.handler(args, ctx)
                err: str | None = None
            except Exception as e:  # noqa: BLE001
                result = None
                err = f"{type(e).__name__}:{str(e)[:200]}"
            duration_ms = int((time.time() - t1) * 1000)
            tc = ToolCall(name=name, args=args, result=result,
                          duration_ms=duration_ms, error=err, turn=turn)
            tool_calls.append(tc)

            if name == "respond":
                final_response = str(args.get("markdown") or args.get("text") or "").strip()
                refs = args.get("citations")
                if isinstance(refs, list):
                    for r in refs:
                        if isinstance(r, dict):
                            citations.append({k: r.get(k) for k in ("ref_code", "type", "locator", "snippet")})
                terminated = "respond"
                respond_seen = True
                await _emit("tool_call_end", {"turn": turn, "name": name, "ok": True})
                break

            if err:
                await _emit("tool_call_error", {"turn": turn, "name": name, "msg": err})
            else:
                await _emit("tool_call_end", {"turn": turn, "name": name, "ok": True,
                                                "duration_ms": duration_ms})
            messages.append({"role": "user",
                              "content": _serialize_tool_result(name, result, err)})

        if respond_seen:
            break

        # ---- 3. Budget guard ----------------------------------------------
        if token_budget is not None and (total_meta.tokens_in + total_meta.tokens_out) > token_budget:
            terminated = "budget"
            error = "token_budget_exceeded"
            break

    return ToolLoopResult(
        final_response=final_response,
        citations=citations,
        tool_calls=tool_calls,
        total_meta=total_meta,
        terminated=terminated,
        error=error,
    )


# ---------------------------------------------------------------------------
# Helper: wrap a sync function so it satisfies the async handler signature
# ---------------------------------------------------------------------------

def make_async_handler(fn: Callable[[dict[str, Any], ToolContext], Any]) -> Callable[
    [dict[str, Any], ToolContext], Awaitable[Any]
]:
    async def _handler(args: dict[str, Any], ctx: ToolContext) -> Any:
        import asyncio

        result = fn(args, ctx)
        if hasattr(result, "__await__"):
            return await result  # type: ignore[no-any-return]
        return await asyncio.to_thread(lambda: result)
    return _handler
