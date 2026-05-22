"""Pairwise transition + terminology harmonizer.

Walks SectionDrafts in outline order. For every (prev, current) pair, asks
editor_llm to rewrite ONLY the opening 1-2 sentences of ``current`` so that:

  1. The transition from ``prev``'s closing sentence flows naturally.
  2. Terminology matches the project terminology table.

The harmonizer DELIBERATELY does NOT rewrite the body — the LLM is forbidden
from touching anything past the opening paragraph. If the LLM call fails or
the harmonized text is suspicious (too long / too short / drops citations),
we fall back to a deterministic term-substitution pass.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses
from app.report.store import DEFAULT_TERMINOLOGY, load_terminology, save_draft
from app.schemas.outline import Outline, OutlineNode
from app.schemas.report import ReportDraft, SectionDraft
from app.server.ws import publish

logger = logging.getLogger("autocsr.report.harmonizer")


def _is_mock() -> bool:
    return os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")


def _ordered_leaves(outline: Outline) -> list[OutlineNode]:
    out: list[OutlineNode] = []
    for n in outline.walk():
        if not n.children:
            out.append(n)
    return out


def _last_paragraph(md: str) -> str:
    parts = [p.strip() for p in md.strip().split("\n\n") if p.strip()]
    return parts[-1] if parts else ""


def _first_paragraph(md: str) -> str:
    parts = [p.strip() for p in md.strip().split("\n\n") if p.strip()]
    # If first paragraph is H2, peel it off
    if parts and parts[0].startswith("##"):
        return parts[1] if len(parts) > 1 else ""
    return parts[0] if parts else ""


def _replace_first_paragraph(md: str, new_para: str) -> str:
    lines = md.strip().split("\n\n")
    if not lines:
        return new_para
    # If H2 is first
    if lines[0].startswith("##"):
        if len(lines) == 1:
            return lines[0] + "\n\n" + new_para
        lines[1] = new_para
    else:
        lines[0] = new_para
    return "\n\n".join(lines)


def _term_substitute(text: str, terms: dict[str, str]) -> str:
    """Deterministic case-sensitive substitution of English keys -> Chinese values."""
    if not text or not terms:
        return text
    out = text
    # Sort by length desc so longer phrases match first
    for k in sorted(terms.keys(), key=len, reverse=True):
        v = terms[k]
        if not k or not v:
            continue
        pattern = re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
        out = pattern.sub(v, out)
    return out


# ---------------------------------------------------------------------------
# Single-pair harmonization
# ---------------------------------------------------------------------------

def _build_harmonize_prompt(
    prev_tail: str,
    current_lead: str,
    title: str,
    terms: dict[str, str],
) -> tuple[str, str]:
    sys_msg = (
        "你负责章节衔接与术语统一。**只能**修改当前章节的开头段落（首段，"
        "不含 H2 标题）让它自然承接上一节末段，并把英文术语统一为指定的中文。"
        "**严格禁止**：删除或编造 Ref 引用、改写正文其它段落、改变数字、加新事实。"
        "只输出修改后的开头段落纯文本，不要 markdown 列表、不要 H2、不要解释。"
    )
    term_lines = "\n".join(f"- {k} -> {v}" for k, v in list(terms.items())[:20])
    user_msg = (
        f"## 上一节末段\n{prev_tail[:500]}\n\n"
        f"## 当前章节标题\n{title}\n\n"
        f"## 当前章节首段（待改写）\n{current_lead[:600]}\n\n"
        f"## 术语对照\n{term_lines or '(none)'}\n\n"
        "请输出改写后的首段（保留原有 Ref 标记，可微调措辞但不得变更数字与事实）："
    )
    return sys_msg, user_msg


async def _harmonize_pair(
    prev: SectionDraft | None,
    current: SectionDraft,
    terms: dict[str, str],
) -> tuple[str, int, int, int]:
    """Return (new_first_paragraph, tokens_in, tokens_out, latency_ms)."""
    import asyncio
    lead = _first_paragraph(current.markdown)
    if not lead.strip():
        return "", 0, 0, 0
    prev_tail = _last_paragraph(prev.markdown) if prev else ""

    if _is_mock():
        # In mock mode just normalize terminology deterministically
        return _term_substitute(lead, terms), 0, 0, 0

    sys_msg, user_msg = _build_harmonize_prompt(prev_tail, lead, current.title, terms)
    policy = _policy.editor_llm()
    t0 = time.time()
    try:
        def _call() -> dict[str, Any]:
            return llm_responses(
                [{"role": "system", "content": sys_msg},
                 {"role": "user", "content": user_msg}],
                timeout=policy.timeout,
                max_tokens=min(policy.max_tokens, 1200),
                temperature=policy.temperature,
                reasoning_effort=policy.reasoning_effort,
            )
        out = await asyncio.to_thread(_call)
        text = (out.get("text") or "").strip()
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
        raw = out.get("raw") or {}
        usage = raw.get("usage") or {}
        ti = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        to = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        latency = int((time.time() - t0) * 1000)
    except (ArkError, Exception) as e:  # noqa: BLE001
        logger.warning("harmonize LLM failed for %s: %s", current.node_id, e)
        return _term_substitute(lead, terms), 0, 0, int((time.time() - t0) * 1000)

    if not text:
        return _term_substitute(lead, terms), ti, to, latency

    # Safety: drop edits that look suspicious
    if len(text) > 3 * max(60, len(lead)) or len(text) < max(20, int(0.3 * len(lead))):
        logger.info("harmonize rejected (length out of bounds) for %s", current.node_id)
        return _term_substitute(lead, terms), ti, to, latency

    # Safety: every Ref<...> in the original lead must survive
    refs_in = set(re.findall(r"Ref[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_.\-]+)?", lead))
    refs_out = set(re.findall(r"Ref[A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_.\-]+)?", text))
    if not refs_in.issubset(refs_out):
        logger.info("harmonize dropped refs in %s; falling back", current.node_id)
        return _term_substitute(lead, terms), ti, to, latency

    return text, ti, to, latency


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def harmonize(
    project_id: str,
    report: ReportDraft,
    outline: Outline,
    by_id: dict[str, OutlineNode] | None = None,
) -> ReportDraft:
    by_id = by_id or {n.id: n for n in outline.walk()}
    terms = load_terminology(project_id) or DEFAULT_TERMINOLOGY
    leaves = _ordered_leaves(outline)
    drafts_dict = report.drafts
    prev: SectionDraft | None = None

    await publish(project_id, "harmonizer.start", {
        "leaves_total": len([n for n in leaves if n.id in drafts_dict]),
    })

    total_in = total_out = 0
    progressed = 0

    for node in leaves:
        cur = drafts_dict.get(node.id)
        if cur is None:
            continue
        try:
            new_lead, ti, to, ms = await _harmonize_pair(prev, cur, terms)
        except Exception as e:  # noqa: BLE001
            logger.exception("harmonize pair crashed")
            await publish(project_id, "harmonizer.progress", {
                "node_id": node.id, "ok": False, "error": str(e)[:160],
            })
            prev = cur
            continue

        total_in += ti
        total_out += to
        if new_lead and new_lead != _first_paragraph(cur.markdown):
            new_md = _replace_first_paragraph(cur.markdown, new_lead)
            cur = cur.model_copy(update={
                "markdown": new_md,
                "status": "harmonized",
                "generated_at": datetime.now(timezone.utc),
            })
            # Update llm_meta tokens additively
            new_meta = cur.llm_meta.model_copy(update={
                "tokens_in": cur.llm_meta.tokens_in + ti,
                "tokens_out": cur.llm_meta.tokens_out + to,
            })
            cur = cur.model_copy(update={"llm_meta": new_meta})
            drafts_dict[node.id] = cur
            save_draft(project_id, cur)
        else:
            cur = cur.model_copy(update={"status": "harmonized"})
            drafts_dict[node.id] = cur
            save_draft(project_id, cur)
        progressed += 1
        await publish(project_id, "harmonizer.progress", {
            "node_id": node.id, "ok": True, "tokens_in": ti, "tokens_out": to, "latency_ms": ms,
        })
        prev = cur

    report = report.model_copy(update={
        "drafts": drafts_dict, "harmonized": True,
    })
    report.total_tokens.input += total_in
    report.total_tokens.output += total_out

    await publish(project_id, "harmonizer.done", {
        "leaves_harmonized": progressed,
        "tokens_in": total_in, "tokens_out": total_out,
    })
    return report
