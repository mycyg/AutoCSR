"""Comments + batch-apply (M11).

CRUD over inline comments + ``apply_all_unresolved`` which feeds every
open comment into ``editor_llm`` and asks it to emit a single set of
patches (via the same protocol as ``chat_editor``). All emitted patches
are applied locally, draft versions are bumped, applied comments get
``status='resolved'`` + ``applied_in_draft_version`` set.

Mock mode (``CSR_EDITOR_MOCK=1`` OR ``CSR_WRITER_MOCK=1``) deterministic
behaviour: for each open comment append a single paragraph
"已按批注 #{id} 修订：{body}" to the target draft + mark resolved.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.config import data_dir
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses as llm_responses
from app.report import store as draft_store
from app.report.chat_editor import _apply_one_patch, _parse_llm_json
from app.report.writer_agent import (
    _extract_refs as _wa_extract_refs,
    _validate_refs as _wa_validate_refs,
    _word_count as _wa_word_count,
)
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.comment import Comment, CommentApplyResult
from app.server.ws import publish

logger = logging.getLogger("autocsr.report.comments")


_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _comments_path(pid: str) -> Path:
    base = data_dir() / "projects" / pid
    base.mkdir(parents=True, exist_ok=True)
    return base / "comments.jsonl"


def _is_mock() -> bool:
    for k in ("CSR_EDITOR_MOCK", "CSR_WRITER_MOCK"):
        if os.environ.get(k, "").lower() in ("1", "true", "yes"):
            return True
    return False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_all(pid: str) -> list[Comment]:
    p = _comments_path(pid)
    if not p.exists():
        return []
    out: list[Comment] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Comment.model_validate_json(line))
        except Exception:
            continue
    return out


def _rewrite_all(pid: str, items: list[Comment]) -> None:
    """Full rewrite — used for status patches & deletion."""
    p = _comments_path(pid)
    with _lock(pid):
        lines = [c.model_dump_json() for c in items]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _append(pid: str, comment: Comment) -> None:
    p = _comments_path(pid)
    with _lock(pid):
        with p.open("a", encoding="utf-8") as f:
            f.write(comment.model_dump_json() + "\n")


def add_comment(pid: str, *, node_id: str, paragraph_idx: int,
                 char_range: tuple[int, int], body: str,
                 author: str = "user") -> Comment:
    c = Comment(
        id=uuid.uuid4().hex[:10],
        project_id=pid,
        node_id=node_id,
        paragraph_idx=int(paragraph_idx),
        char_range=(int(char_range[0]), int(char_range[1])),
        body=body,
        author=author,
        status="open",
        created_at=datetime.now(timezone.utc),
    )
    _append(pid, c)
    return c


def list_comments(pid: str, *, node_id: str | None = None,
                   status: str | None = None) -> list[Comment]:
    items = _load_all(pid)
    if node_id:
        items = [c for c in items if c.node_id == node_id]
    if status:
        items = [c for c in items if c.status == status]
    return items


def update_comment(pid: str, cid: str, *, status: str | None = None,
                    body: str | None = None) -> Comment | None:
    items = _load_all(pid)
    updated: Comment | None = None
    for i, c in enumerate(items):
        if c.id == cid:
            patch: dict[str, Any] = {}
            if status is not None and status in ("open", "resolved", "rejected"):
                patch["status"] = status
            if body is not None:
                patch["body"] = body
            items[i] = c.model_copy(update=patch)
            updated = items[i]
            break
    if updated is None:
        return None
    _rewrite_all(pid, items)
    return updated


def delete_comment(pid: str, cid: str) -> bool:
    items = _load_all(pid)
    new = [c for c in items if c.id != cid]
    if len(new) == len(items):
        return False
    _rewrite_all(pid, new)
    return True


# ---------------------------------------------------------------------------
# Batch apply via editor_llm
# ---------------------------------------------------------------------------

def _build_batch_prompt(node_id: str, draft_md: str,
                        comments: list[Comment]) -> tuple[str, str]:
    sys = (
        "你是 CSR 章节批注处理助手。给定章节当前 markdown 和若干批注，"
        "你需要输出最小改动的 JSON 补丁应用所有可处理的批注。"
        "禁止编造引用代码，禁止跨节修改。\n\n"
        "## 协议\n"
        '{"actions": [{"tool": "apply_patch", "args": {'
        '"op": "replace_paragraph|insert_paragraph|patch_field|replace_section", '
        '"target": int或正则字符串, "after": "新文本", "comment_id": "对应批注 id"}}, ...]}\n'
        "每个 apply_patch 必带 comment_id；其他 tool 一律忽略。"
    )
    com_lines = []
    for c in comments:
        com_lines.append(
            f"- id={c.id}  段落 {c.paragraph_idx}  range [{c.char_range[0]},{c.char_range[1]}]: "
            f"{c.body[:200]}"
        )
    user = (
        f"## 当前章节 {node_id}\n```\n{draft_md}\n```\n\n"
        f"## 批注列表\n{chr(10).join(com_lines)}\n\n"
        "请用最小改动逐条响应；如某批注无法机械应用（需人工判断），"
        "可省略其 patch，最终输出 JSON 即可。"
    )
    return sys, user


def _mock_batch(draft_md: str, comments: list[Comment]) -> dict[str, Any]:
    """Deterministic: 1 insert_paragraph at end per comment."""
    actions = []
    for c in comments:
        actions.append({
            "tool": "apply_patch",
            "args": {
                "op": "insert_paragraph",
                "target": -1,
                "after": f"已按批注 #{c.id} 修订：{c.body[:80]}",
                "comment_id": c.id,
            },
        })
    return {"actions": actions}


async def apply_all_unresolved(project_id: str) -> CommentApplyResult:
    """Process every open comment via editor_llm and apply patches."""
    items = _load_all(project_id)
    open_items = [c for c in items if c.status == "open"]
    result = CommentApplyResult(project_id=project_id)
    if not open_items:
        return result

    # Group by node_id so the LLM sees one draft at a time
    by_node: dict[str, list[Comment]] = {}
    for c in open_items:
        by_node.setdefault(c.node_id, []).append(c)

    resolved_ids: set[str] = set()
    new_versions: dict[str, int] = {}
    warnings: list[str] = []

    for node_id, comments in by_node.items():
        draft = draft_store.load_draft(project_id, node_id)
        if draft is None:
            warnings.append(f"no_draft_for_node:{node_id}")
            result.skipped_count += len(comments)
            continue

        sys_msg, user_msg = _build_batch_prompt(node_id, draft.markdown, comments)

        if _is_mock():
            payload = _mock_batch(draft.markdown, comments)
        else:
            policy = _policy.editor_llm()
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
                text = (out.get("text") or "").strip()
                try:
                    payload = _parse_llm_json(text)
                except json.JSONDecodeError as je:
                    warnings.append(f"llm_json_error:{node_id}:{je}")
                    result.skipped_count += len(comments)
                    continue
            except (ArkError, Exception) as e:  # noqa: BLE001
                warnings.append(f"llm_error:{node_id}:{type(e).__name__}:{str(e)[:120]}")
                result.skipped_count += len(comments)
                continue

        current_md = draft.markdown
        n_applied_here = 0
        applied_comment_ids: list[str] = []
        for raw in (payload.get("actions") or []):
            if not isinstance(raw, dict) or raw.get("tool") != "apply_patch":
                continue
            args = raw.get("args") or {}
            if not isinstance(args, dict):
                continue
            op = str(args.get("op") or "").strip()
            target = args.get("target")
            after = str(args.get("after") or "")
            comment_id = str(args.get("comment_id") or "")
            try:
                new_md, _before = _apply_one_patch(current_md, op, target, after)
            except ValueError as e:
                warnings.append(f"patch_failed:{comment_id}:{e}")
                continue
            current_md = new_md
            n_applied_here += 1
            if comment_id:
                applied_comment_ids.append(comment_id)

        if n_applied_here == 0:
            result.skipped_count += len(comments)
            continue

        # Re-validate refs + save versioned snapshot
        refs = _wa_extract_refs(current_md)
        cits, ref_warnings = _wa_validate_refs(project_id, refs)
        warnings.extend(ref_warnings)
        new_draft = draft.model_copy(update={
            "markdown": current_md,
            "citations": cits,
            "word_count": _wa_word_count(current_md),
            "generated_at": datetime.now(timezone.utc),
            "warnings": (draft.warnings or []) + ref_warnings + ["batch_comments_applied"],
            "status": "draft",
        })
        draft_store.save_draft(project_id, new_draft)
        new_v = draft_store.snapshot_draft(project_id, new_draft)
        new_versions[node_id] = new_v
        result.applied_count += n_applied_here

        # Mark applied comments resolved
        for cid in applied_comment_ids:
            resolved_ids.add(cid)
            for i, c in enumerate(items):
                if c.id == cid:
                    items[i] = c.model_copy(update={
                        "status": "resolved",
                        "applied_in_draft_version": new_v,
                    })
                    break

    if resolved_ids:
        _rewrite_all(project_id, items)

    result.new_versions = new_versions
    result.warnings = warnings
    try:
        from app.server.routes.alerts import invalidate as _alerts_invalidate
        _alerts_invalidate(project_id)
        await publish(project_id, "alerts.updated", {"source": "comments"})
    except Exception:
        pass
    await publish(project_id, "comment.applied", {
        "applied_count": result.applied_count,
        "new_versions": result.new_versions,
        "skipped_count": result.skipped_count,
    })
    return result


# ---------------------------------------------------------------------------
# BaseAgent wrapper
# ---------------------------------------------------------------------------

class CommentApplyAgent(BaseAgent):
    """Apply all unresolved comments under one project."""

    name = "CommentApplier"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        try:
            result = await apply_all_unresolved(agent_input.project_id)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"comments.apply failed: {e}", cause=e)
        return AgentOutput(
            ok=True, result=result.model_dump(),
            warnings=list(result.warnings or []),
        )
