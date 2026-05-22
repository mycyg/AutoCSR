"""Built-in tools every agent can hand to ``tool_loop.run_tool_loop``.

The handlers stay small + boring — they wrap existing AutoCSR services so a
writer / editor LLM can request:

  * ``sandbox_python(code)`` — execute Python under M7 isolation
  * ``search_corpus(query, types?, top_k?)`` — corpus retrieval
  * ``fetch_ref(ref_code)`` — resolve a Ref<...> back to its block
  * ``read_stat_block(stat_id)`` — return one StatBlock (full markdown_table)
  * ``read_section(node_id)`` — return the existing draft of a section
  * ``call_analyst(query, scope?)`` — delegate to analyst_agent (writes a new
    StatBlock + returns its ref_code). May go through a FuturePool so two
    writers asking the same thing in parallel share the same run.
  * ``respond(markdown, citations?)`` — stop the loop and emit the final
    section markdown.

Every handler is plain Python — async only where the underlying call is.
"""
from __future__ import annotations

import json
from typing import Any

from app.agents.tool_loop import ToolContext, ToolSpec
from app.analysis.store import get as get_stat
from app.corpus.index import fetch_ref as corpus_fetch_ref, search as corpus_search
from app.report.store import load_draft
from app.sandbox.executor import execute_python


# ---------------------------------------------------------------------------
# Sandbox python tool
# ---------------------------------------------------------------------------

async def _h_sandbox_python(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    import asyncio

    code = str(args.get("code") or "")
    if not code.strip():
        raise ValueError("code is required")
    timeout = int(args.get("timeout") or 30)
    mem_mb = int(args.get("mem_mb") or 512)

    def _run() -> dict[str, Any]:
        res = execute_python(
            ctx.project_id, code, timeout=timeout, mem_mb=mem_mb,
        )
        return {
            "run_id": res.run_id,
            "exit_code": res.exit_code,
            "error": res.error,
            "stdout": res.stdout[-4000:],
            "stderr": res.stderr[-1500:],
            "artifacts": list(res.artifacts),
            "duration_ms": res.duration_ms,
        }

    ctx.extra.setdefault("sandbox_calls", 0)
    ctx.extra["sandbox_calls"] += 1
    return await asyncio.to_thread(_run)


sandbox_python_tool = ToolSpec(
    name="sandbox_python",
    description="在隔离 Python 沙盒里执行一小段数据分析代码，stdout / artifacts 都会返回。",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "timeout": {"type": "integer", "minimum": 1, "maximum": 60},
            "mem_mb": {"type": "integer", "minimum": 64, "maximum": 2048},
        },
        "required": ["code"],
    },
    handler=_h_sandbox_python,
)


# ---------------------------------------------------------------------------
# Search corpus
# ---------------------------------------------------------------------------

async def _h_search_corpus(args: dict[str, Any], ctx: ToolContext) -> list[dict[str, Any]]:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    types = args.get("types") or []
    if isinstance(types, str):
        types = [types]
    top_k = int(args.get("top_k") or 5)
    hits = corpus_search(ctx.project_id, query, types=types or None, top_k=top_k)
    out: list[dict[str, Any]] = []
    for h in hits:
        out.append({
            "ref_code": h.ref_code,
            "type": h.block.type,
            "snippet": h.snippet,
            "score": h.score,
        })
    return out


search_corpus_tool = ToolSpec(
    name="search_corpus",
    description="按关键词在 corpus 中检索 literature/stat/principle/note 块。",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "types": {"type": "array", "items": {"type": "string"}},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
    handler=_h_search_corpus,
)


# ---------------------------------------------------------------------------
# Fetch one ref
# ---------------------------------------------------------------------------

async def _h_fetch_ref(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any] | None:
    ref = str(args.get("ref_code") or "").strip()
    if not ref:
        raise ValueError("ref_code is required")
    block = corpus_fetch_ref(ctx.project_id, ref)
    if block is None:
        return None
    return {
        "ref_code": ref,
        "type": block.type,
        "text": (block.text or "")[:2000],
        "meta": block.meta or {},
    }


fetch_ref_tool = ToolSpec(
    name="fetch_ref",
    description="给定 Ref<...> 编码，拉回原始 block 内容（截断 2000 字）。",
    input_schema={
        "type": "object",
        "properties": {"ref_code": {"type": "string"}},
        "required": ["ref_code"],
    },
    handler=_h_fetch_ref,
)


# ---------------------------------------------------------------------------
# Read stat block
# ---------------------------------------------------------------------------

async def _h_read_stat_block(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any] | None:
    sid = str(args.get("stat_id") or "").strip()
    if not sid:
        raise ValueError("stat_id is required")
    sb = get_stat(ctx.project_id, sid)
    if sb is None:
        return None
    return {
        "id": sb.id,
        "title": sb.title,
        "analysis_type": sb.analysis_type,
        "markdown_table": sb.markdown_table,
        "ref_code": sb.ref_code,
        "source_files": sb.source_files,
    }


read_stat_block_tool = ToolSpec(
    name="read_stat_block",
    description="按 StatBlock id 取整块（含完整 markdown 表格）。",
    input_schema={
        "type": "object",
        "properties": {"stat_id": {"type": "string"}},
        "required": ["stat_id"],
    },
    handler=_h_read_stat_block,
)


# ---------------------------------------------------------------------------
# Read section (previously drafted)
# ---------------------------------------------------------------------------

async def _h_read_section(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any] | None:
    node_id = str(args.get("node_id") or "").strip()
    if not node_id:
        raise ValueError("node_id is required")
    draft = load_draft(ctx.project_id, node_id)
    if draft is None:
        return None
    return {
        "node_id": draft.node_id,
        "title": draft.title,
        "markdown": draft.markdown,
        "word_count": draft.word_count,
        "status": draft.status,
    }


read_section_tool = ToolSpec(
    name="read_section",
    description="读已写好的章节 markdown（同一份报告里其他章节）。",
    input_schema={
        "type": "object",
        "properties": {"node_id": {"type": "string"}},
        "required": ["node_id"],
    },
    handler=_h_read_section,
)


# ---------------------------------------------------------------------------
# call_analyst — defers to analyst_agent (with optional FuturePool dedup)
# ---------------------------------------------------------------------------

async def _h_call_analyst(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    scope = str(args.get("scope") or "all")
    if not query:
        raise ValueError("query is required")

    pool = ctx.extra.get("analyst_pool")
    if pool is not None:
        # FuturePool dedups identical analyst queries inside one orchestrator run
        # (see report.orchestrator)
        try:
            result = await pool.request(ctx.project_id, query, scope)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"analyst_pool.request failed: {e}")
    else:
        from app.agents.analyst_agent import run_analyst

        result = await run_analyst(ctx.project_id, query, scope=scope)

    sb = (result or {}).get("stat_block") or {}
    return {
        "stat_id": sb.get("id"),
        "ref_code": sb.get("ref_code"),
        "title": sb.get("title"),
        "markdown_table": sb.get("markdown_table"),
        "chart_json_present": bool((sb.get("result_json") or {}).get("chart_json")),
        "sandbox_run_id": (result or {}).get("sandbox_run_id"),
    }


call_analyst_tool = ToolSpec(
    name="call_analyst",
    description="用一句自然语言让 analyst agent 跑一次自定义分析（沙盒里写代码 + 出表/图）。返回 StatBlock 简要信息。",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "scope": {"type": "string"},
        },
        "required": ["query"],
    },
    handler=_h_call_analyst,
)


# ---------------------------------------------------------------------------
# respond — terminates the loop
# ---------------------------------------------------------------------------

async def _h_respond(args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    return {"markdown": args.get("markdown", ""), "ok": True}


respond_tool = ToolSpec(
    name="respond",
    description="结束本次工具循环，把最终章节 markdown 放进 args.markdown。",
    input_schema={
        "type": "object",
        "properties": {
            "markdown": {"type": "string"},
            "citations": {"type": "array"},
        },
        "required": ["markdown"],
    },
    handler=_h_respond,
)


# ---------------------------------------------------------------------------
# Convenience bundles
# ---------------------------------------------------------------------------

WRITER_TOOLS: list[ToolSpec] = [
    sandbox_python_tool,
    search_corpus_tool,
    fetch_ref_tool,
    read_stat_block_tool,
    read_section_tool,
    call_analyst_tool,
    respond_tool,
]


def writer_tools(*, exclude: list[str] | None = None) -> list[ToolSpec]:
    """Return WRITER_TOOLS minus any names in ``exclude``."""
    excl = set(exclude or [])
    return [t for t in WRITER_TOOLS if t.name not in excl]
