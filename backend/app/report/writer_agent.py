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
from app.schemas.report import CitationRef, LLMMeta, SectionDraft

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
    sys_msg = (
        "你是临床研究报告（CSR / ICH E3）的章节作者。严格遵循以下风格指南，"
        "所有数字必须有引用，禁止编造任何 Ref 代码或数据。\n\n"
        f"{style_guide}\n\n"
        f"## 项目术语对照\n{_format_terminology(ctx.terminology)}\n"
    )
    parts: list[str] = []
    parts.append(f"## 当前章节\n- ID: {node.id}\n- 标题: {node.title}\n- 层级: H{node.level + 1}")
    if ctx.parent_summary:
        parts.append(f"\n## 父章节摘要\n{ctx.parent_summary[:600]}")
    if ctx.sibling_tail:
        parts.append(f"\n## 前一节末句\n{ctx.sibling_tail[:300]}")
    if requirements:
        bullet = "\n".join(f"- {r}" for r in requirements[:12])
        parts.append(f"\n## 硬性要求（来自原则）\n{bullet}")
    if node.notes:
        parts.append(f"\n## 写作提示\n{node.notes}")
    if stat_ev:
        for i, s in enumerate(stat_ev, 1):
            parts.append(f"\n## 统计证据 #{i} [{s['ref_code']}] — {s['title']}\n{s['markdown_table']}")
    if lit_ev:
        parts.append("\n## 文献证据")
        for l in lit_ev:
            parts.append(f"- [{l['ref_code']}]: {l['text']}")
    if ctx.extra_instructions:
        parts.append(f"\n## 重写补充说明\n{ctx.extra_instructions}")
    parts.append(
        f"\n## 输出要求\n"
        f"- 用 Markdown 写本节正文（**从 H2 开始**，**不要**重复 H1 标题）。\n"
        f"- 篇幅约 {ctx.max_words // 2}~{ctx.max_words} 字（中文计字）。\n"
        f"- 至少引用 1 处证据；每处数字后紧跟 [Ref<...>]。\n"
        f"- 不要输出 ```markdown 代码块，仅纯 markdown 文本。\n"
        f"- 不要在末尾追加额外的「参考文献」列表，引用通过行内 [Ref<...>] 表达。"
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

    t0 = time.time()
    markdown = ""
    via = "mock"
    tokens_in = tokens_out = 0
    warnings: list[str] = []
    status: str = "draft"

    if _is_mock():
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
    )
    return draft
