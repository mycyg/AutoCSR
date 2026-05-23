"""Per-project WebSocket hub.

Single endpoint /ws/{pid} accepting clients that subscribe to events for one
project. Event taxonomy (best-effort, additive):

  router.start                {}
  router.file_classified      {file_id, ingest_type, confidence}
  router.all_done             {}
  worker.start                {file_id, ingest_type}
  worker.progress             {file_id, message}
  worker.done                 {file_id, ingest_type, artifacts, notes}
  worker.error                {file_id, error}
  cleansing.applying          {file_id, proposal_id}
  cleansing.apply_done        {file_id, snapshot_id}
  cleansing.rollback          {snapshot_id}
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.jwt_token import decode_token
from app.auth.middleware import _dev_mode_enabled, _ensure_dev_seed_user
from app.auth.models import get_user_by_id
from app.projects.manager import ensure_project_access

logger = logging.getLogger("autocsr.ws")
router = APIRouter()

# In-memory subscribers: { project_id -> set[WebSocket] }
_SUBS: dict[str, set[WebSocket]] = defaultdict(set)
_LOCK = asyncio.Lock()


async def _add(pid: str, ws: WebSocket) -> None:
    async with _LOCK:
        _SUBS[pid].add(ws)


async def _remove(pid: str, ws: WebSocket) -> None:
    async with _LOCK:
        _SUBS[pid].discard(ws)
        if not _SUBS[pid]:
            _SUBS.pop(pid, None)


async def publish(project_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Fan out one event to all subscribers of a project."""
    payload = payload or {}
    messages = [
        json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False),
    ]
    try:
        from app.server.task_events import normalize_task_event
        normalized = normalize_task_event(project_id, event_type, payload)
        if normalized is not None:
            messages.append(json.dumps({
                "type": "task.event",
                "payload": normalized.model_dump(),
            }, ensure_ascii=False))
    except Exception:
        logger.debug("task_event_normalize_failed", exc_info=True)
    dead: list[WebSocket] = []
    async with _LOCK:
        targets = list(_SUBS.get(project_id, set()))
    for ws in targets:
        try:
            for msg in messages:
                await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        await _remove(project_id, ws)


def publish_sync(project_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Schedule a publish from sync code (best-effort; drops if no running loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    asyncio.ensure_future(publish(project_id, event_type, payload), loop=loop)


@router.websocket("/ws/{pid}")
async def project_ws(ws: WebSocket, pid: str) -> None:
    try:
        token = ws.query_params.get("token") or ""
        user = None
        if token:
            claims = decode_token(token)
            if claims.get("typ") != "access":
                raise ValueError("not an access token")
            user = get_user_by_id(str(claims.get("sub") or ""))
            if user is None:
                raise ValueError("user not found")
        elif _dev_mode_enabled():
            uid = ws.headers.get("x-user-id") or "demo_author"
            user = _ensure_dev_seed_user(uid)
        if user is None:
            raise ValueError("authentication required")
        ensure_project_access(user, pid, "read")
    except Exception:
        await ws.close(code=1008)
        return
    await ws.accept()
    await _add(pid, ws)
    logger.info("ws subscribed pid=%s", pid)
    try:
        await ws.send_text(json.dumps({"type": "hello", "payload": {"project_id": pid}}))
        # Keepalive loop — accept any inbound text but ignore (clients may ping).
        while True:
            try:
                await ws.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        with contextlib.suppress(Exception):
            await _remove(pid, ws)
        logger.info("ws closed pid=%s", pid)
