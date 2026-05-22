"""Chat / version routes (M5).

Endpoints:
  POST   /api/projects/{pid}/chapters/{node_id}/chat
  GET    /api/projects/{pid}/chapters/{node_id}/chat
  DELETE /api/projects/{pid}/chapters/{node_id}/chat/{msg_id}
  POST   /api/projects/{pid}/report/drafts/{node_id}/rollback/{version}
  GET    /api/projects/{pid}/report/drafts/{node_id}/versions
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.config import data_dir
from app.outline.store import load as load_outline
from app.report.chat_editor import chat_turn
from app.report.store import (
    append_chat_message, assemble_report, delete_chat_message,
    list_versions, load_chat_history, load_draft, restore_version,
    save_report,
)
from app.schemas.chat import ChatMessage
from app.server.ws import publish

logger = logging.getLogger("autocsr.report.chat_routes")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


def _hist_to_models(items: list[dict[str, Any]]) -> list[ChatMessage]:
    out: list[ChatMessage] = []
    for it in items:
        try:
            out.append(ChatMessage.model_validate(it))
        except Exception:
            continue
    return out


@router.post("/projects/{pid}/chapters/{node_id}/chat")
async def post_chat(pid: str, node_id: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    if load_draft(pid, node_id) is None:
        raise HTTPException(status_code=404, detail=f"draft {node_id} not found — generate it first")
    message = str(body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message must be non-empty")

    history = _hist_to_models(load_chat_history(pid, node_id))
    await publish(pid, "chat.assistant_thinking", {"node_id": node_id})
    try:
        result = await chat_turn(pid, node_id, message, history)
    except Exception as e:
        logger.exception("chat_turn failed")
        await publish(pid, "chat.error", {"node_id": node_id, "error": str(e)[:200]})
        raise HTTPException(status_code=500, detail=f"chat_turn failed: {e}")

    # Refresh assembled report so subsequent /report calls see new markdown
    outline = load_outline(pid)
    if outline is not None:
        save_report(assemble_report(pid, outline.version, harmonized=False))

    if result.patches:
        await publish(pid, "chat.patch_applied", {
            "node_id": node_id,
            "n_patches": len(result.patches),
            "new_version": result.new_version,
        })
    await publish(pid, "chat.turn_done", {
        "node_id": node_id,
        "assistant_id": result.assistant_message.id,
        "new_version": result.new_version,
    })
    return result.model_dump()


@router.get("/projects/{pid}/chapters/{node_id}/chat")
def get_chat(pid: str, node_id: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return load_chat_history(pid, node_id)


@router.delete("/projects/{pid}/chapters/{node_id}/chat/{msg_id}")
def delete_chat(pid: str, node_id: str, msg_id: str) -> dict[str, bool]:
    _ensure_project(pid)
    return {"ok": delete_chat_message(pid, node_id, msg_id)}


@router.get("/projects/{pid}/report/drafts/{node_id}/versions")
def get_versions(pid: str, node_id: str) -> list[int]:
    _ensure_project(pid)
    return list_versions(pid, node_id)


@router.put("/projects/{pid}/report/drafts/{node_id}/markdown")
async def put_draft_markdown(pid: str, node_id: str, body: dict = Body(...)) -> dict[str, Any]:
    """Manual edit: overwrite a section's markdown and snapshot as a new version.

    Citations are re-validated against the project corpus + stat store so the
    UI can refresh the cite list immediately. This is the persistence channel
    for the ChapterReader's MdEditor "lock/unlock" mode.
    """
    _ensure_project(pid)
    draft = load_draft(pid, node_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"draft {node_id} not found")
    new_md = body.get("markdown")
    if not isinstance(new_md, str):
        raise HTTPException(status_code=400, detail="markdown must be a string")
    from datetime import datetime, timezone
    from app.report.store import save_draft, snapshot_draft
    from app.report.writer_agent import (
        _extract_refs as _wa_extract_refs,
        _validate_refs as _wa_validate_refs,
        _word_count as _wa_word_count,
    )
    refs = _wa_extract_refs(new_md)
    citations, ref_warnings = _wa_validate_refs(pid, refs)
    new_warns = list(draft.warnings or []) + ref_warnings + ["manual_edit"]
    updated = draft.model_copy(update={
        "markdown": new_md,
        "citations": citations,
        "word_count": _wa_word_count(new_md),
        "generated_at": datetime.now(timezone.utc),
        "status": "draft",
        "warnings": new_warns,
    })
    save_draft(pid, updated)
    version = snapshot_draft(pid, updated)
    outline = load_outline(pid)
    if outline is not None:
        save_report(assemble_report(pid, outline.version, harmonized=False))
    await publish(pid, "chat.manual_edit", {"node_id": node_id, "version": version})
    return {"draft": updated.model_dump(), "version": version}


@router.post("/projects/{pid}/report/drafts/{node_id}/rollback/{version}")
async def rollback_version(pid: str, node_id: str, version: int) -> dict[str, Any]:
    _ensure_project(pid)
    restored = restore_version(pid, node_id, version)
    if restored is None:
        raise HTTPException(
            status_code=404, detail=f"version {version} of {node_id} not found",
        )
    outline = load_outline(pid)
    if outline is not None:
        save_report(assemble_report(pid, outline.version, harmonized=False))
    await publish(pid, "chat.rolled_back", {
        "node_id": node_id, "version": version,
    })
    return restored.model_dump()
