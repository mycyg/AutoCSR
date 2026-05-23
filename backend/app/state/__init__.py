"""Project state machine + M15 lock / blinding guards."""
from app.state import blinding, lock
from app.state.machine import (
    ProjectState,
    ProjectStateMachine,
    StateTransitionError,
    machine as default_machine,
)

__all__ = [
    "ProjectState",
    "ProjectStateMachine",
    "StateTransitionError",
    "default_machine",
    "blinding",
    "lock",
]


def guard_locked(pid: str, request=None) -> None:
    """Raise HTTPException 403 if the project is database-locked and the
    request does not carry ``X-Addendum: true``. Callable from any
    mutation route."""
    if not lock.is_locked(pid):
        return
    addendum = False
    if request is not None:
        try:
            addendum = str(request.headers.get("X-Addendum") or "").lower() in ("1", "true", "yes")
        except Exception:
            addendum = False
    if addendum:
        return
    from fastapi import HTTPException
    raise HTTPException(
        status_code=403,
        detail="project database is locked; pass X-Addendum: true to record an addendum",
    )
