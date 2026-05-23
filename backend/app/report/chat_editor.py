"""Conversational section editor (M5).

Given a section's current markdown plus a user message, ask `editor_llm` what
to do. The LLM is given a small tool surface:

  * read_current()                       — returns the section markdown
  * apply_patch(op, target?, after)      — mutate the section
        op ∈ {replace_section, insert_paragraph, replace_paragraph, patch_field}
  * search_corpus(query, types?, top_k?) — fetch supporting evidence
  * respond(message)                     — chat-only reply (no edit)

The LLM emits a JSON-only response shaped like:

    {
      "actions": [
        {"tool": "apply_patch", "args": {"op": "replace_paragraph", "target": 1,
                                         "after": "..."}},
        {"tool": "respond",     "args": {"message": "已把第二段改正式。"}}
      ]
    }

Each `apply_patch` is executed locally, a new SectionDraft version snapshot
is taken, citations are re-validated, and a `Patch` record with the
before/after delta is returned for the frontend's diff view.

Audit trail: every turn (user + assistant) is appended to
``data/projects/<pid>/chats/<node_id>.jsonl``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.corpus.index import search as corpus_search
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses
from app.report import store as draft_store
from app.report.writer_agent import (
    _extract_refs as _wa_extract_refs,
    _validate_refs as _wa_validate_refs,
    _word_count as _wa_word_count,
)
from app.schemas.chat import ChatMessage, ChatTurnResult, Patch
from app.schemas.report import Provenance, SectionDraft

logger = logging.getLogger("autocsr.report.chat_editor")

_STYLE_GUIDE_PATH = Path(__file__).with_name("style_guide.md")


def _read_style_guide() -> str:
    try:
        return _STYLE_GUIDE_PATH.read_text(encoding="utf-8")[:4000]
    except Exception:
        return ""


def _is_mock() -> bool:
    return os.environ.get("CSR_EDITOR_MOCK", "").lower() in ("1", "true", "yes") \
        or os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def _split_paragraphs(md: str) -> list[str]:
    # Split on blank-line boundaries. Empty trailing strings are removed.
    parts = re.split(r"\n\s*\n", md.strip("\n"))
    return [p for p in parts]


def _join_paragraphs(paragraphs: Iterable[str]) -> str:
    return "\n\n".join(p.rstrip() for p in paragraphs if p is not None) + "\n"


def _apply_one_patch(markdown: str, op: str, target: Any, after: str) -> tuple[str, str]:
    """Apply one patch to `markdown` and return (new_markdown, before_excerpt).

    Raises ValueError when the op cannot be applied (caller surfaces it as a
    chat error rather than crashing the request).
    """
    if op == "replace_section":
        before = markdown
        return (after if after.endswith("\n") else after + "\n"), before
    paras = _split_paragraphs(markdown)
    if op == "insert_paragraph":
        try:
            idx = int(target if target is not None else len(paras))
        except (TypeError, ValueError):
            raise ValueError(f"insert_paragraph requires int target, got {target!r}")
        # Clamp into [0, len(paras)] so callers can append by passing -1 or huge n
        if idx < 0:
            idx = len(paras) + 1 + idx
        idx = max(0, min(idx, len(paras)))
        new = paras[:idx] + [after] + paras[idx:]
        return _join_paragraphs(new), ""
    if op == "replace_paragraph":
        try:
            idx = int(target)
        except (TypeError, ValueError):
            raise ValueError(f"replace_paragraph requires int target, got {target!r}")
        if not (0 <= idx < len(paras)):
            raise ValueError(f"replace_paragraph: index {idx} out of range (n={len(paras)})")
        before = paras[idx]
        new = list(paras)
        new[idx] = after
        return _join_paragraphs(new), before
    if op == "patch_field":
        if not isinstance(target, str) or not target:
            raise ValueError("patch_field requires a non-empty regex/literal target")
        try:
            pattern = re.compile(target)
        except re.error:
            # Fall back to literal substitution
            if target in markdown:
                return markdown.replace(target, after, 1), target
            raise ValueError(f"patch_field: target {target!r} not found in section")
        m = pattern.search(markdown)
        if m is None:
            raise ValueError(f"patch_field: pattern {target!r} did not match")
        before = m.group(0)
        new_md = markdown[:m.start()] + after + markdown[m.end():]
        return new_md, before
    raise ValueError(f"unknown patch op: {op!r}")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(section_title: str, current_markdown: str, style: str,
                          language: str = "zh") -> str:
    try:
        from app.i18n.loader import render_prompt
        return render_prompt(
            "editor",
            language=language,
            section_title=section_title,
            current_markdown=current_markdown,
            style=style[:1200],
        )
    except Exception:
        return f"""你是 CSR (ICH E3) 章节编辑助手。仅修改当前章节内容；不得编造引用代码。

## 当前章节
标题: {section_title}

## 当前 Markdown
```
{current_markdown}
```

## 风格摘要
{style[:1200]}

## 输出协议
**只输出 JSON**，结构：
{{"actions": [{{"tool": "apply_patch" | "search_corpus" | "respond", "args": {{...}}}}]}}
"""


def _mock_actions(user_message: str, markdown: str) -> dict[str, Any]:
    """Deterministic fallback used in unit/e2e tests."""
    paras = _split_paragraphs(markdown)
    if not paras:
        return {"actions": [{"tool": "respond",
                              "args": {"message": "本节为空，无法编辑。"}}]}
    # If the user asks for "formal"/"正式"/"删除"/"加" we touch para 0 with a marker.
    msg_lc = user_message.lower()
    if any(kw in user_message for kw in ("正式", "改写", "重写", "重述")) or "formal" in msg_lc:
        new_para = paras[0] + "（已按要求调整为更正式的措辞。）"
        return {"actions": [
            {"tool": "apply_patch", "args": {
                "op": "replace_paragraph", "target": 0, "after": new_para,
            }},
            {"tool": "respond", "args": {
                "message": f"已把第 1 段改写为更正式的版本（mock 模式）；用户请求：{user_message[:40]}",
            }},
        ]}
    # default: just respond
    snippet = user_message[:80]
    return {"actions": [{"tool": "respond", "args": {
        "message": f"（mock 模式）收到：{snippet}。当前章节共 {len(paras)} 段。",
    }}]}


def _parse_llm_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    # Greedy isolate the outermost {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
    else:
        candidate = text
    return json.loads(candidate)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


async def chat_turn(
    project_id: str,
    node_id: str,
    user_message: str,
    chat_history: list[ChatMessage] | None = None,
) -> ChatTurnResult:
    """One conversation turn.

    Side effects: writes audit log, may produce one or more SectionDraft
    version snapshots. Returns the assistant message + patches.
    """
    history = chat_history or []
    draft = draft_store.load_draft(project_id, node_id)
    if draft is None:
        raise RuntimeError(f"draft for {node_id} not found")

    # 1) Persist the user message immediately
    user_msg = ChatMessage(
        id=uuid.uuid4().hex[:12], role="user", content=user_message,
        patches=[], ts=_now(),
    )
    draft_store.append_chat_message(project_id, node_id,
                                    json.loads(user_msg.model_dump_json()))

    # 2) Snapshot pre-edit version so rollback always has a target
    pre_versions = draft_store.list_versions(project_id, node_id)
    if not pre_versions:
        draft_store.snapshot_draft(project_id, draft)

    try:
        from app.report.orchestrator import _load_project_language
        _lang = _load_project_language(project_id)
    except Exception:
        _lang = "zh"
    sys_msg = _build_system_prompt(
        draft.title or node_id, draft.markdown, _read_style_guide(), _lang,
    )

    # 3) Call the LLM (or mock)
    actions_payload: dict[str, Any]
    llm_meta: dict[str, Any] = {"via": "mock", "tokens_in": 0, "tokens_out": 0}
    if _is_mock():
        actions_payload = _mock_actions(user_message, draft.markdown)
    else:
        policy = _policy.editor_llm()
        # Add up to 6 most-recent history turns for context
        history_lines = []
        for m in history[-6:]:
            role = "用户" if m.role == "user" else "助手"
            history_lines.append(f"{role}: {m.content[:300]}")
        prior = "\n".join(history_lines) or "(无)"
        user_full = (
            f"## 历史对话\n{prior}\n\n"
            f"## 本次用户消息\n{user_message}\n"
        )
        try:
            def _call() -> dict[str, Any]:
                return llm_responses(
                    [{"role": "system", "content": sys_msg},
                     {"role": "user", "content": user_full}],
                    timeout=policy.timeout,
                    max_tokens=policy.max_tokens,
                    temperature=policy.temperature,
                    reasoning_effort=policy.reasoning_effort,
                    project_id=project_id,
                    caller_agent="chat_editor",
                )
            out = await asyncio.to_thread(_call)
            text = (out.get("text") or "").strip()
            llm_meta["via"] = out.get("via") or "llm"
            usage = (out.get("raw") or {}).get("usage") or {}
            llm_meta["tokens_in"] = int(usage.get("prompt_tokens",
                                                  usage.get("input_tokens", 0)) or 0)
            llm_meta["tokens_out"] = int(usage.get("completion_tokens",
                                                   usage.get("output_tokens", 0)) or 0)
            try:
                actions_payload = _parse_llm_json(text)
            except json.JSONDecodeError as je:
                logger.warning("editor LLM produced non-JSON: %s ; head=%r", je, text[:200])
                actions_payload = {"actions": [{
                    "tool": "respond",
                    "args": {"message": f"（LLM 返回无法解析的格式，原文：{text[:200]}）"},
                }]}
        except (ArkError, Exception) as e:  # noqa: BLE001
            logger.warning("editor LLM failed: %s", e)
            actions_payload = {"actions": [{
                "tool": "respond",
                "args": {"message": f"（编辑器 LLM 失败：{type(e).__name__}: {str(e)[:160]}）"},
            }]}

    # 4) Execute actions
    patches: list[Patch] = []
    chat_response_parts: list[str] = []
    new_warnings: list[str] = []
    new_version: int | None = None
    current_md = draft.markdown
    updated_draft = draft

    for raw in (actions_payload.get("actions") or []):
        if not isinstance(raw, dict):
            continue
        tool = raw.get("tool")
        args = raw.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if tool == "respond":
            msg = str(args.get("message") or "").strip()
            if msg:
                chat_response_parts.append(msg)
            continue
        if tool == "search_corpus":
            query = str(args.get("query") or "").strip()
            types = args.get("types") or None
            top_k = int(args.get("top_k") or 5)
            if not query:
                continue
            try:
                hits = corpus_search(project_id, query,
                                     types=tuple(types) if types else None,
                                     top_k=top_k)
                if hits:
                    snippets = [f"[{h.ref_code}] {h.snippet[:140]}" for h in hits[:5]]
                    chat_response_parts.append(
                        "检索到证据：\n" + "\n".join(snippets),
                    )
                else:
                    chat_response_parts.append(f"未检索到「{query}」相关证据。")
            except Exception as e:  # noqa: BLE001
                new_warnings.append(f"search_corpus_failed:{type(e).__name__}")
            continue
        if tool == "apply_patch":
            op = str(args.get("op") or "").strip()
            target = args.get("target")
            after = str(args.get("after") or "")
            note = str(args.get("note") or "")
            # M15: a patch initiated by the LLM is 'hybrid'; chat_editor
            # never sees a pure-human edit (those go through the markdown
            # PATCH route below). Caller can override via args.source.
            patch_source = str(args.get("source") or "hybrid").lower()
            if patch_source not in ("hybrid", "human", "ai"):
                patch_source = "hybrid"
            try:
                new_md, before = _apply_one_patch(current_md, op, target, after)
            except ValueError as e:
                new_warnings.append(f"patch_failed:{op}:{str(e)[:120]}")
                chat_response_parts.append(f"补丁未应用：{e}")
                continue
            # Re-validate citations on the new markdown
            refs = _wa_extract_refs(new_md)
            citations, ref_warnings = _wa_validate_refs(project_id, refs)
            new_warnings.extend(ref_warnings)
            # Re-derive provenance: keep existing 'ai' baseline span,
            # append a hybrid/human span covering the new section.
            new_prov = list(updated_draft.provenance or [])
            new_prov.append(Provenance(
                range=(0, len(new_md)),
                source=patch_source,  # type: ignore[arg-type]
                confidence=0.9 if patch_source == "hybrid" else 1.0,
                agent_name="chat_editor",
                ts=_now(),
            ))
            # M17 — re-run hallucination guard on the patched markdown
            extra_warnings: list[str] = []
            try:
                from app.safety.hallucination_guard import (
                    mark_provenance_hallucinations,
                    validate_references_against_corpus,
                )
                _hg = validate_references_against_corpus(
                    new_md, project_id, node_id=updated_draft.node_id,
                )
                if _hg:
                    new_prov = mark_provenance_hallucinations(new_prov, _hg)
                    extra_warnings.append(f"hallucination:{len(_hg)} unresolved refs")
            except Exception:
                pass
            updated_draft = updated_draft.model_copy(update={
                "markdown": new_md,
                "citations": citations,
                "word_count": _wa_word_count(new_md),
                "generated_at": _now(),
                "warnings": (updated_draft.warnings or []) + ref_warnings + extra_warnings,
                "status": "draft",
                "provenance": new_prov,
            })
            draft_store.save_draft(project_id, updated_draft)
            new_version = draft_store.snapshot_draft(project_id, updated_draft)
            current_md = new_md
            patches.append(Patch(
                op=op,  # type: ignore[arg-type]
                target=target if isinstance(target, (int, str)) else None,
                before=before,
                after=after,
                applied=True,
                note=note,
            ))
            continue
        # Unknown tool — surface a warning
        new_warnings.append(f"unknown_tool:{tool}")

    if not chat_response_parts:
        chat_response_parts.append("（已处理，无额外说明。）")

    assistant_msg = ChatMessage(
        id=uuid.uuid4().hex[:12], role="assistant",
        content="\n\n".join(chat_response_parts),
        patches=patches, ts=_now(),
        meta={
            "llm_via": llm_meta["via"],
            "tokens_in": llm_meta["tokens_in"],
            "tokens_out": llm_meta["tokens_out"],
            "new_version": new_version,
        },
    )
    draft_store.append_chat_message(project_id, node_id,
                                    json.loads(assistant_msg.model_dump_json()))

    return ChatTurnResult(
        assistant_message=assistant_msg,
        patches=patches,
        new_version=new_version,
        new_warnings=new_warnings,
    )
