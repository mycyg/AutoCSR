"""In-memory + arq-compatible queue runtime.

Task type → handler registration is via :func:`register_handler`.
Existing call sites can keep using ``asyncio.create_task`` directly;
new call sites can switch to ``enqueue`` for cancellable + observable
background work.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.config import settings

logger = logging.getLogger("autocsr.queue")

Handler = Callable[..., Awaitable[Any]]


@dataclass
class TaskRecord:
    id: str
    task_type: str
    project_id: str | None = None
    status: str = "queued"            # queued | running | done | error | cancelled
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    backend: str = "inmemory"
    cancel_requested: bool = False


_LOCK = threading.RLock()
_TASKS: dict[str, TaskRecord] = {}
_ASYNCIO_TASKS: dict[str, asyncio.Task] = {}
_HANDLERS: dict[str, Handler] = {}


def register_handler(task_type: str, handler: Handler) -> None:
    _HANDLERS[task_type] = handler


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backend() -> str:
    # Env override takes precedence so docker-compose can flip the
    # backend without rebuilding the image.
    env = (os.environ.get("AUTOCSR_QUEUE_BACKEND") or "").strip().lower()
    if env in {"inmemory", "arq"}:
        return env
    seg = settings().get("queue") or {}
    return str(seg.get("backend") or "inmemory").lower()


def enqueue(task_type: str, payload: dict[str, Any] | None = None,
            *, project_id: str | None = None,
            timeout_s: float | None = None) -> str:
    """Schedule ``task_type`` for execution. Returns the task_id."""
    handler = _HANDLERS.get(task_type)
    if handler is None:
        raise ValueError(f"no handler registered for task_type {task_type!r}")
    rec = TaskRecord(
        id="job_" + uuid.uuid4().hex[:12],
        task_type=task_type,
        project_id=project_id,
        created_at=_now(),
        backend=_backend(),
    )
    with _LOCK:
        _TASKS[rec.id] = rec

    backend = _backend()
    if backend == "arq":
        # arq backend stub: try to enqueue via redis. If it fails (no
        # redis / no arq), gracefully fall through to inmemory so the
        # caller stays observable.
        try:
            _enqueue_arq(rec, handler, payload or {})
            return rec.id
        except Exception as e:  # noqa: BLE001
            logger.warning("arq enqueue failed (%s) — falling back to inmemory", e)
            rec.backend = "inmemory"
            with _LOCK:
                _TASKS[rec.id] = rec

    # Inmemory path
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    async def _runner() -> None:
        with _LOCK:
            rec.status = "running"
            rec.started_at = _now()
        try:
            res = await asyncio.wait_for(
                handler(**(payload or {})),
                timeout=timeout_s,
            )
            with _LOCK:
                rec.status = "done"
                rec.progress = 1.0
                rec.result = _truncate_result(res)
                rec.finished_at = _now()
        except asyncio.CancelledError:
            with _LOCK:
                rec.status = "cancelled"
                rec.finished_at = _now()
            raise
        except Exception as e:  # noqa: BLE001
            with _LOCK:
                rec.status = "error"
                rec.error = f"{type(e).__name__}: {str(e)[:300]}"
                rec.finished_at = _now()

    if loop is None:
        # No running loop — execute synchronously via a fresh loop. This
        # is only hit from CLI smoke tests.
        asyncio.run(_runner())
    else:
        task = loop.create_task(_runner())
        with _LOCK:
            _ASYNCIO_TASKS[rec.id] = task
    return rec.id


def _truncate_result(res: Any) -> Any:
    """Avoid storing huge results inline — keep just the shape."""
    if res is None:
        return None
    try:
        import json
        text = json.dumps(res, default=str, ensure_ascii=False)
        if len(text) > 50_000:
            return {"truncated": True, "len": len(text), "head": text[:1000]}
        return res
    except Exception:
        return {"type": type(res).__name__}


def get_status(task_id: str) -> TaskRecord | None:
    with _LOCK:
        rec = _TASKS.get(task_id)
        if rec is None:
            return None
        return TaskRecord(**asdict(rec))


def cancel(task_id: str) -> bool:
    with _LOCK:
        rec = _TASKS.get(task_id)
        if rec is None:
            return False
        rec.cancel_requested = True
        task = _ASYNCIO_TASKS.get(task_id)
    if task is not None and not task.done():
        task.cancel()
        return True
    return False


def list_recent(*, project_id: str | None = None, limit: int = 50) -> list[TaskRecord]:
    with _LOCK:
        items = list(_TASKS.values())
    if project_id:
        items = [t for t in items if t.project_id == project_id]
    items.sort(key=lambda t: t.created_at or "", reverse=True)
    return [TaskRecord(**asdict(t)) for t in items[:limit]]


# ---------------------------------------------------------------------------
# arq backend (best-effort, optional)
# ---------------------------------------------------------------------------

def _redis_url() -> str:
    env = os.environ.get("AUTOCSR_REDIS_URL")
    if env:
        return env
    seg = settings().get("queue") or {}
    return str(seg.get("redis_url") or "redis://127.0.0.1:6379/0")


def _enqueue_arq(rec: TaskRecord, handler: Handler, payload: dict) -> None:
    """Submit to arq if installed + reachable. Raises on any failure
    so the caller can degrade to inmemory cleanly."""
    try:
        from arq.connections import RedisSettings, create_pool  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"arq not installed: {e}")
    url = _redis_url()

    # Synchronously create + enqueue via a temp loop. If a loop is already
    # running (FastAPI handler), schedule on a side-thread to avoid the
    # "asyncio.run() cannot be called from a running event loop" error.
    async def _go() -> None:
        pool = await create_pool(RedisSettings.from_dsn(url))
        try:
            await pool.enqueue_job(rec.task_type, **payload, _job_id=rec.id)
        finally:
            await pool.close()

    try:
        asyncio.get_running_loop()
        # We're inside an event loop — run in a thread with its own loop.
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as pool_exec:
            fut = pool_exec.submit(asyncio.run, _go())
            fut.result(timeout=10)
    except RuntimeError:
        asyncio.run(_go())
