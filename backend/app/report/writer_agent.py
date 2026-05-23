"""Single-section writer agent.

Given one OutlineNode plus the project's WriterContext, this agent:

1. Loads the style guide + terminology table.
2. Fetches every StatBlock that the outline node has bound (stat_refs).
3. Pulls extra literature hits via corpus search using node title + parent path.
4. Builds a strict system + user prompt and calls writer_llm.
5. Verifies every Ref<...> referenced in the output against corpus/stat stores.
6. Returns a SectionDraft with citations + LLM meta.

The agent is **defensive**: any LLM failure / mock mode emits a stub
SectionDraft so the orchestrator can keep going.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.analysis.store import get as get_stat
from app.corpus.index import fetch_ref, parse_ref, search as corpus_search
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses
from app.schemas.outline import OutlineNode
from app.schemas.report import CitationRef, LLMMeta, Provenance, SectionDraft

logger = logging.getLogger("autocsr.report.writer")

_STYLE_GUIDE_PATH = Path(__file__).with_name("style_guide.md")


def _read_style_guide() -> str:
    try:
        return _STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


class WriterContext(BaseModel):
    """Per-section call context."""
    project_id: str
    parent_summary: str = ""               # short summary of parent / preceding context
    sibling_tail: str = ""                 # last 1-2 sentences of the previous sibling section
    terminology: dict[str, str] = Field(default_factory=dict)
    extra_instructions: str = ""           # optional override for regenerate / editor
    max_words: int = 600                   # target upper bound; prompt only, soft
    language: str = "zh"                   # M13 — drives prompt template language
    # M9 — tool loop knobs
    enable_tools: bool = False             # when True, writer drives an LLM ↔ tool loop
    max_tool_turns: int = 5
    available_tools: list[str] | None = None  # subset of builtin tool names; None=all
    analyst_pool: Any = None               # FuturePool injected by orchestrator (M9)

    class Config:
        arbitrary_types_allowed = True


# ---------------------------------------------------------------------------
# Reference extraction + validation
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(r"Ref[A-Za-z0-9_\-]+(?:\.(?:P\d+\.Col\d+\.Para\d+|var[A-Za-z0-9_\-]+|S[A-Za-z0-9_.\-]+))?")


def _extract_refs(markdown: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _REF_PATTERN.finditer(markdown):
        ref = m.group(0)
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def _validate_refs(project_id: str, refs: list[str]) -> tuple[list[CitationRef], list[str]]:
    """Return (citations, warnings) — citations include every ref that resolved."""
    citations: list[CitationRef] = []
    warnings: list[str] = []
    for ref in refs:
        parsed = parse_ref(ref)
        if not parsed:
            warnings.append(f"unparseable_ref:{ref}")
            continue
        kind = parsed["kind"]
        block = None
        try:
            block = fetch_ref(project_id, ref)
        except Exception:
            block = None
        # Fall back: stat blocks live in stats store too
        if block is None and kind == "stat":
            bid = parsed.get("bid") or ""
            sb = get_stat(project_id, bid)
            if sb is not None:
                citations.append(CitationRef(
                    ref_code=ref, type="stat", locator=f"[{ref}]",
                    snippet=(sb.title or "")[:120],
                ))
                continue
        if block is None:
            warnings.append(f"missing_ref:{ref}")
            continue
        snippet = (block.text or "")[:120].replace("\n", " ")
        citations.append(CitationRef(
            ref_code=ref, type=kind, locator=f"[{ref}]", snippet=snippet,
        ))
    return citations, warnings


# ---------------------------------------------------------------------------
# Evidence assembly
# ---------------------------------------------------------------------------

def _load_evidence(
    project_id: str,
    node: OutlineNode,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (stat_evidence, lit_evidence) where each item carries ref_code +
    short text/markdown suitable for prompt injection."""
    stat_ev: list[dict[str, Any]] = []
    for ref in node.stat_refs or []:
        try:
            block = fetch_ref(project_id, ref)
        except Exception:
            block = None
        if block is None:
            # try via stat store directly
            parsed = parse_ref(ref) or {}
            bid = parsed.get("bid") or ""
            sb = get_stat(project_id, bid)
            if sb is not None:
                stat_ev.append({
                    "ref_code": ref,
                    "title": sb.title,
                    "markdown_table": (sb.markdown_table or "")[:1800],
                })
            continue
        stat_ev.append({
            "ref_code": ref,
            "title": block.meta.get("title") or "stat block",
            "markdown_table": (block.text or "")[:1800],
        })

    lit_ev: list[dict[str, Any]] = []
    for ref in node.literature_refs or []:
        try:
            block = fetch_ref(project_id, ref)
        except Exception:
            block = None
        if block is None:
            continue
        lit_ev.append({
            "ref_code": ref,
            "text": (block.text or "")[:600],
        })

    # Top-up: literature search by title if we have <3 lit refs
    if len(lit_ev) < 3:
        try:
            hits = corpus_search(project_id, node.title, types=("literature",), top_k=5)
        except Exception:
            hits = []
        for h in hits:
            if any(l["ref_code"] == h.ref_code for l in lit_ev):
                continue
            lit_ev.append({
                "ref_code": h.ref_code,
                "text": (h.block.text or "")[:600],
            })
            if len(lit_ev) >= 5:
                break
    return stat_ev, lit_ev[:5]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _format_terminology(terms: dict[str, str]) -> str:
    if not terms:
        return "(none)"
    lines = [f"- {k} -> {v}" for k, v in list(terms.items())[:30]]
    return "\n".join(lines)


def _principle_requirements(node: OutlineNode) -> list[str]:
    """Best-effort lookup of section requirements from the principle ref."""
    if not node.principle_ref:
        return []
    parsed = parse_ref(node.principle_ref)
    if not parsed or parsed.get("kind") != "principle":
        return []
    try:
        from app.principles import load_principle  # type: ignore
        principle_id = parsed.get("pid")
        if not principle_id:
            return []
        principle = load_principle(principle_id)
    except Exception:
        return []
    sid = parsed.get("sid") or node.id
    # Flat-walk the principle tree
    stack = list(principle.sections)
    while stack:
        s = stack.pop()
        if getattr(s, "id", None) == sid:
            return list(getattr(s, "requirements", []) or [])
        stack.extend(getattr(s, "children", []) or [])
    return []


def _build_prompt(
    node: OutlineNode,
    ctx: WriterContext,
    stat_ev: list[dict[str, Any]],
    lit_ev: list[dict[str, Any]],
    requirements: list[str],
    style_guide: str,
) -> tuple[str, str]:
    lang = (ctx.language or "zh").lower()
    # M13 — load the localized system prompt with fallback.
    try:
        from app.i18n.loader import render_prompt
        sys_msg = render_prompt(
            "writer",
            language=lang,
            style_guide=style_guide,
            terminology_block=_format_terminology(ctx.terminology),
        )
    except Exception:
        sys_msg = (
            "你是临床研究报告（CSR / ICH E3）的章节作者。严格遵循以下风格指南，"
            "所有数字必须有引用，禁止编造任何 Ref 代码或数据。\n\n"
            f"{style_guide}\n\n"
            f"## 项目术语对照\n{_format_terminology(ctx.terminology)}\n"
        )

    parts: list[str] = []
    if lang.startswith("en"):
        labels = {
            "section": "Current section",
            "id": "ID", "title": "Title", "level": "Level",
            "parent": "Parent summary", "prev": "Previous section tail",
            "req": "Hard requirements (from principle)",
            "notes": "Writing notes", "stat": "Statistical evidence",
            "lit": "Literature evidence",
            "extra": "Rewrite extra instructions",
            "out_header": "Output requirements",
            "out_md": "- Use Markdown for the section body (**start at H2**, **do NOT** repeat the H1 title).",
            "out_len": f"- Aim for {ctx.max_words // 2}~{ctx.max_words} words.",
            "out_cite": "- Cite at least one piece of evidence; place [Ref<...>] right after every number.",
            "out_fence": "- Do not wrap output in a ```markdown fence — emit raw markdown only.",
            "out_no_refs_section": "- Do not append a 'References' list — all citations live inline as [Ref<...>].",
        }
    else:
        labels = {
            "section": "当前章节",
            "id": "ID", "title": "标题", "level": "层级",
            "parent": "父章节摘要", "prev": "前一节末句",
            "req": "硬性要求（来自原则）",
            "notes": "写作提示", "stat": "统计证据",
            "lit": "文献证据",
            "extra": "重写补充说明",
            "out_header": "输出要求",
            "out_md": "- 用 Markdown 写本节正文（**从 H2 开始**，**不要**重复 H1 标题）。",
            "out_len": f"- 篇幅约 {ctx.max_words // 2}~{ctx.max_words} 字（中文计字）。",
            "out_cite": "- 至少引用 1 处证据；每处数字后紧跟 [Ref<...>]。",
            "out_fence": "- 不要输出 ```markdown 代码块，仅纯 markdown 文本。",
            "out_no_refs_section": "- 不要在末尾追加额外的「参考文献」列表，引用通过行内 [Ref<...>] 表达。",
        }
    parts.append(f"## {labels['section']}\n- {labels['id']}: {node.id}\n- {labels['title']}: {node.title}\n- {labels['level']}: H{node.level + 1}")
    if ctx.parent_summary:
        parts.append(f"\n## {labels['parent']}\n{ctx.parent_summary[:600]}")
    if ctx.sibling_tail:
        parts.append(f"\n## {labels['prev']}\n{ctx.sibling_tail[:300]}")
    if requirements:
        bullet = "\n".join(f"- {r}" for r in requirements[:12])
        parts.append(f"\n## {labels['req']}\n{bullet}")
    if node.notes:
        parts.append(f"\n## {labels['notes']}\n{node.notes}")
    if stat_ev:
        for i, s in enumerate(stat_ev, 1):
            parts.append(f"\n## {labels['stat']} #{i} [{s['ref_code']}] — {s['title']}\n{s['markdown_table']}")
    if lit_ev:
        parts.append(f"\n## {labels['lit']}")
        for l in lit_ev:
            parts.append(f"- [{l['ref_code']}]: {l['text']}")
    if ctx.extra_instructions:
        parts.append(f"\n## {labels['extra']}\n{ctx.extra_instructions}")
    parts.append(
        f"\n## {labels['out_header']}\n"
        f"{labels['out_md']}\n"
        f"{labels['out_len']}\n"
        f"{labels['out_cite']}\n"
        f"{labels['out_fence']}\n"
        f"{labels['out_no_refs_section']}"
    )
    return sys_msg, "\n".join(parts)


# ---------------------------------------------------------------------------
# Mock mode for offline e2e
# ---------------------------------------------------------------------------

def _mock_section(node: OutlineNode, stat_ev: list[dict[str, Any]], lit_ev: list[dict[str, Any]]) -> str:
    refs: list[str] = []
    refs.extend(s["ref_code"] for s in stat_ev[:2])
    refs.extend(l["ref_code"] for l in lit_ev[:1])
    ref_marks = " ".join(f"[{r}]" for r in refs)
    return (
        f"## {node.title}\n\n"
        f"本节为 {node.id} 「{node.title}」 的占位草稿（mock 模式）。该章节涵盖"
        f"{node.notes or '相应分析与文献综述'}，详细数据见绑定的统计块 {ref_marks}。\n\n"
        f"研究纳入人群与基线特征对应章节 10 描述；本节按硬性要求"
        f"逐条对应：包括分析集定义、变量定义、假设检验方法与结果呈现。"
        f" {ref_marks}\n"
    )


def _word_count(md: str) -> int:
    # Cheap Chinese-aware count: each CJK ideograph + each whitespace-delimited Latin token.
    cjk = sum(1 for ch in md if "一" <= ch <= "鿿")
    latin_tokens = len([t for t in re.split(r"\s+", re.sub(r"[一-鿿]+", " ", md)) if t])
    return cjk + latin_tokens


def _is_mock() -> bool:
    return os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Tool loop adapter (M9)
# ---------------------------------------------------------------------------

async def _run_writer_tool_loop(
    *,
    project_id: str,
    node: OutlineNode,
    ctx: "WriterContext",
    sys_msg: str,
    user_msg: str,
    llm_policy: _policy.LLMPolicy,
) -> Any:
    """Drive the LLM ↔ tool loop for one section.

    Returns a ``ToolLoopResult``.
    """
    from app.agents.builtin_tools import writer_tools
    from app.agents.tool_loop import ToolContext, run_tool_loop
    from app.server.ws import publish

    avail = ctx.available_tools
    tools = writer_tools(exclude=[t.name for t in writer_tools()
                                    if avail is not None and t.name not in avail and t.name != "respond"])
    tool_ctx = ToolContext(
        project_id=project_id,
        node_id=node.id,
        extra={
            "analyst_pool": ctx.analyst_pool,
            "node_title": node.title,
        },
    )

    async def _emit(kind: str, payload: dict[str, Any]) -> None:
        # Translate ToolLoop events into writer.subphase / writer.tool_call_*
        try:
            if kind == "turn_start":
                await publish(project_id, "writer.subphase", {
                    "node_id": node.id, "phase": "thinking",
                    "turn": payload.get("turn"),
                })
            elif kind == "tool_call_start":
                phase = "tool"
                name = payload.get("name") or ""
                if name == "sandbox_python":
                    phase = "sandbox-running"
                elif name == "call_analyst":
                    phase = "calling-analyst"
                elif name == "search_corpus":
                    phase = "searching"
                elif name == "respond":
                    phase = "drafting"
                await publish(project_id, "writer.subphase", {
                    "node_id": node.id, "phase": phase, "tool_call": name,
                })
                await publish(project_id, "writer.tool_call_start", {
                    "node_id": node.id, "name": name,
                    "args_preview": _short_args(payload.get("args")),
                    "turn": payload.get("turn"),
                })
            elif kind == "tool_call_end":
                await publish(project_id, "writer.tool_call_end", {
                    "node_id": node.id,
                    "name": payload.get("name"),
                    "duration_ms": payload.get("duration_ms"),
                    "turn": payload.get("turn"),
                    "ok": payload.get("ok", True),
                })
            elif kind == "tool_call_error":
                await publish(project_id, "writer.tool_call_error", {
                    "node_id": node.id,
                    "name": payload.get("name"),
                    "msg": payload.get("msg"),
                    "turn": payload.get("turn"),
                })
        except Exception:
            pass

    final_user_msg = (
        f"{user_msg}\n\n"
        "## 工作流程\n"
        "1. 先评估需要哪些证据：用 `search_corpus` 找文献；用 `read_stat_block` 读已绑定的统计块；如需新分析就 `call_analyst` 或 `sandbox_python`。\n"
        "2. 拿到证据后调用 `respond` 提交最终 markdown，把数字和 [Ref<...>] 一一对应。\n"
    )

    return await run_tool_loop(
        system_prompt=sys_msg,
        user_messages=[{"role": "user", "content": final_user_msg}],
        tools=tools,
        ctx=tool_ctx,
        llm_policy=llm_policy,
        max_turns=int(ctx.max_tool_turns or 5),
        on_event=_emit,
    )


def _short_args(value: Any) -> Any:
    """Trim verbose args (especially long code strings) before publishing."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, str) and len(v) > 200:
                out[k] = v[:200] + "…"
            else:
                out[k] = v
        return out
    return value


def _save_tool_history(project_id: str, node_id: str, meta: dict[str, Any]) -> None:
    """Append a writer-tool-call history file for the section."""
    from app.config import data_dir as _data_dir
    safe = node_id.replace("/", "_")
    base = _data_dir() / "projects" / project_id / "chapters"
    base.mkdir(parents=True, exist_ok=True)
    p = base / f"{safe}_tools.jsonl"
    with p.open("a", encoding="utf-8") as f:
        for tc in meta.get("tool_calls") or []:
            f.write(re.sub(r"\s+", " ",
                            __import__("json").dumps(tc, ensure_ascii=False, default=str)).strip() + "\n")


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def write_section(
    project_id: str,
    outline_node: OutlineNode,
    context: WriterContext | None = None,
    *,
    llm_policy: _policy.LLMPolicy | None = None,
) -> SectionDraft:
    import asyncio
    ctx = context or WriterContext(project_id=project_id)
    style_guide = _read_style_guide()
    stat_ev, lit_ev = _load_evidence(project_id, outline_node)
    requirements = _principle_requirements(outline_node)
    sys_msg, user_msg = _build_prompt(outline_node, ctx, stat_ev, lit_ev, requirements, style_guide)

    # M15: when project is blinded, mask arm names in BOTH the system and
    # user messages so the LLM never sees raw arm labels.
    try:
        from app.state import blinding as _blinding
        if _blinding.is_blinded(project_id):
            mapping = _blinding.arm_map(project_id)
            if mapping:
                sys_msg = _blinding.mask_arms(sys_msg, mapping)
                user_msg = _blinding.mask_arms(user_msg, mapping)
                warnings_seed = ["blinded:arms_masked"]
            else:
                warnings_seed = []
        else:
            warnings_seed = []
    except Exception:
        warnings_seed = []

    t0 = time.time()
    markdown = ""
    via = "mock"
    tokens_in = tokens_out = 0
    warnings: list[str] = list(warnings_seed)
    status: str = "draft"
    tool_loop_meta: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Mode A: tool loop (M9) — real LLM with self-service tools
    # ------------------------------------------------------------------
    if ctx.enable_tools and not _is_mock():
        try:
            tl_result = await _run_writer_tool_loop(
                project_id=project_id, node=outline_node, ctx=ctx,
                sys_msg=sys_msg, user_msg=user_msg,
                llm_policy=llm_policy or _policy.writer_llm(),
            )
            markdown = (tl_result.final_response or "").strip()
            via = "llm-tools"
            tokens_in = tl_result.total_meta.tokens_in
            tokens_out = tl_result.total_meta.tokens_out
            tool_loop_meta = {
                "terminated": tl_result.terminated,
                "n_tool_calls": len(tl_result.tool_calls),
                "tool_calls": [tc.to_dict() for tc in tl_result.tool_calls],
                "citations": tl_result.citations,
            }
            if tl_result.terminated != "respond":
                warnings.append(f"tool_loop_terminated:{tl_result.terminated}")
            if not markdown:
                # fall through to mock so the orchestrator can keep going
                markdown = _mock_section(outline_node, stat_ev, lit_ev)
                via = "fallback"
                status = "error"
                warnings.append("tool_loop_empty_response")
            # Persist tool-call history for the section
            try:
                _save_tool_history(project_id, outline_node.id, tool_loop_meta)
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            logger.warning("writer tool loop failed for %s: %s", outline_node.id, e)
            warnings.append(f"tool_loop_error:{type(e).__name__}:{str(e)[:160]}")
            markdown = _mock_section(outline_node, stat_ev, lit_ev)
            via = "fallback"
            status = "error"

    # ------------------------------------------------------------------
    # Mode B: legacy single-shot LLM or mock
    # ------------------------------------------------------------------
    elif _is_mock():
        markdown = _mock_section(outline_node, stat_ev, lit_ev)
        via = "mock"
    else:
        policy = llm_policy or _policy.writer_llm()
        try:
            def _call() -> dict[str, Any]:
                return llm_responses(
                    [{"role": "system", "content": sys_msg},
                     {"role": "user", "content": user_msg}],
                    timeout=policy.timeout,
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                    reasoning_effort=policy.reasoning_effort,
                    project_id=project_id,
                    caller_agent="writer",
                )
            out = await asyncio.to_thread(_call)
            markdown = (out.get("text") or "").strip()
            via = out.get("via") or "llm"
            raw = out.get("raw") or {}
            usage = raw.get("usage") or {}
            tokens_in = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
            tokens_out = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        except (ArkError, Exception) as e:  # noqa: BLE001
            logger.warning("writer LLM failed for %s: %s", outline_node.id, e)
            warnings.append(f"llm_error:{type(e).__name__}:{str(e)[:160]}")
            # Fallback to mock so the orchestrator keeps going
            markdown = _mock_section(outline_node, stat_ev, lit_ev)
            via = "fallback"
            status = "error"

    # Strip a possible H1 if the model ignored instructions
    markdown = re.sub(r"^# [^\n]+\n+", "", markdown).strip()
    if not markdown.startswith("##"):
        markdown = f"## {outline_node.title}\n\n{markdown}"

    refs = _extract_refs(markdown)
    citations, ref_warnings = _validate_refs(project_id, refs)
    warnings.extend(ref_warnings)

    # Hard constraint: if the node has stat_refs, require at least one citation
    if outline_node.stat_refs and not citations:
        warnings.append("no_citation_but_stat_refs_present")

    latency_ms = int((time.time() - t0) * 1000)
    # M15: mark whole-section content as AI-authored. chat_editor turns
    # patches will downgrade individual ranges to hybrid/human as needed.
    provenance = [Provenance(
        range=(0, len(markdown)),
        source="ai",
        confidence=1.0 if via in ("llm", "llm-tools") else 0.5,
        agent_name="writer",
        ts=datetime.now(timezone.utc),
    )]
    # M17 — flag any Ref<...> the writer invented (unresolved against
    # the corpus / stat / principle stores). Failure to import / scan is
    # silent so older e2e harnesses without those modules still pass.
    try:
        from app.safety.hallucination_guard import (
            mark_provenance_hallucinations, validate_references_against_corpus,
        )
        _hg = validate_references_against_corpus(
            markdown, project_id, node_id=outline_node.id,
        )
        if _hg:
            provenance = mark_provenance_hallucinations(provenance, _hg)
            warnings.append(f"hallucination:{len(_hg)} unresolved refs")
    except Exception:
        pass
    draft = SectionDraft(
        node_id=outline_node.id,
        title=outline_node.title,
        markdown=markdown,
        citations=citations,
        word_count=_word_count(markdown),
        generated_at=datetime.now(timezone.utc),
        llm_meta=LLMMeta(
            model=(llm_policy.name if llm_policy else _policy.writer_llm().name),
            tokens_in=tokens_in, tokens_out=tokens_out,
            latency_ms=latency_ms, via=via,
        ),
        warnings=warnings,
        status=status if status == "error" else "draft",
        provenance=provenance,
    )
    return draft
