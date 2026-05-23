"""Task queue abstraction (M16).

Two backends:

  * ``inmemory`` (default) — wraps ``asyncio.create_task``; status is
    tracked in a process-local dict. This matches the pre-M16 behaviour
    so no existing route gets broken.
  * ``arq``        — opt-in Redis-backed queue; selected by setting
    ``queue.backend: arq`` in settings.yaml. Requires the ``arq``
    package + a reachable Redis.

Public surface:
    enqueue(task_type, payload, *, project_id=None) -> task_id
    get_status(task_id) -> TaskStatus dict
    cancel(task_id) -> bool
"""
from app.queue.runtime import (  # noqa: F401
    TaskRecord, cancel, enqueue, get_status, list_recent,
)
