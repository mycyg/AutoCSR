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
    msg = json.dumps({"type": event_type, "payload": payload or {}}, ensure_ascii=False)
    dead: list[WebSocket] = []
    async with _LOCK:
        targets = list(_SUBS.get(project_id, set()))
    for ws in targets:
        try:
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
