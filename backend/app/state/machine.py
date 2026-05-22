"""Per-project state machine.

Tracks where a project sits in the AutoCSR pipeline so the frontend and tests
can ask "is this project done with cleansing?". State is persisted as
``data/projects/<pid>/state.json`` and guarded by a filelock (with a
threading.RLock fallback) so concurrent transitions never corrupt the file.

State graph (forward-only by default; idempotent self-transitions allowed):

    created -> uploaded -> cleansed -> analyzed -> outlined
            -> writing -> harmonized -> editing -> exported

Some "lateral" transitions are also legal because the user can re-enter a
phase from a later one (re-edit, re-export, re-cleanse after a new upload):

    editing -> writing                (regenerate one section)
    harmonized -> editing             (open chat editor)
    exported -> editing               (download, then continue editing)
    any state -> uploaded             (user uploads new files)
    any state -> cleansed             (re-apply cleansing after upload)

Best-effort: if a backwards transition is attempted that is not in the
allowed table, :class:`StateTransitionError` is raised.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from filelock import FileLock, Timeout as FileLockTimeout
    _HAS_FILELOCK = True
except ImportError:  # pragma: no cover
    FileLock = None  # type: ignore[assignment]
    FileLockTimeout = Exception  # type: ignore[assignment]
    _HAS_FILELOCK = False

from app.config import data_dir
from app.observability.logger import get_logger


class ProjectState(str, Enum):
    """The pipeline phases a project can sit in."""
    created = "created"
    uploaded = "uploaded"
    cleansed = "cleansed"
    analyzed = "analyzed"
    outlined = "outlined"
    writing = "writing"
    harmonized = "harmonized"
    editing = "editing"
    exported = "exported"


# Allowed forward + lateral transitions. Self-transitions are added
# automatically by the machine (idempotent).
_ALLOWED: dict[ProjectState, set[ProjectState]] = {
    ProjectState.created: {
        ProjectState.uploaded,
    },
    ProjectState.uploaded: {
        ProjectState.uploaded,           # additional uploads
        ProjectState.cleansed,
    },
    ProjectState.cleansed: {
        ProjectState.uploaded,           # add more files
        ProjectState.cleansed,           # re-cleanse another file
        ProjectState.analyzed,
    },
    ProjectState.analyzed: {
        ProjectState.uploaded,
        ProjectState.cleansed,
        ProjectState.analyzed,
        ProjectState.outlined,
    },
    ProjectState.outlined: {
        ProjectState.uploaded,
        ProjectState.cleansed,
        ProjectState.analyzed,
        ProjectState.outlined,
        ProjectState.writing,
    },
    ProjectState.writing: {
        ProjectState.outlined,
        ProjectState.writing,
        ProjectState.harmonized,
    },
    ProjectState.harmonized: {
        ProjectState.outlined,
        ProjectState.writing,
        ProjectState.harmonized,
        ProjectState.editing,
        ProjectState.exported,
    },
    ProjectState.editing: {
        ProjectState.writing,
        ProjectState.editing,
        ProjectState.harmonized,
        ProjectState.exported,
    },
    ProjectState.exported: {
        ProjectState.editing,
        ProjectState.exported,
        # allow further re-runs after a new upload
        ProjectState.uploaded,
        ProjectState.cleansed,
        ProjectState.analyzed,
        ProjectState.outlined,
        ProjectState.writing,
        ProjectState.harmonized,
    },
}


class StateTransitionError(Exception):
    """Raised when a transition violates the state graph."""


class ProjectStateMachine:
    """File-backed FSM with WS notification on every transition."""

    def __init__(self) -> None:
        self.logger = get_logger("ProjectStateMachine")
        # Fallback per-pid threading locks when filelock isn't available
        self._tlocks: dict[str, threading.RLock] = {}
        self._tlock_master = threading.RLock()

    # ------------------------------------------------------------------
    # Paths + locking
    # ------------------------------------------------------------------
    def _project_dir(self, pid: str) -> Path:
        return data_dir() / "projects" / pid

    def _state_file(self, pid: str) -> Path:
        return self._project_dir(pid) / "state.json"

    def _lock_file(self, pid: str) -> Path:
        return self._project_dir(pid) / "state.lock"

    def _get_tlock(self, pid: str) -> threading.RLock:
        with self._tlock_master:
            lock = self._tlocks.get(pid)
            if lock is None:
                lock = threading.RLock()
                self._tlocks[pid] = lock
            return lock

    def _acquire(self, pid: str):
        """Return a context manager for the project's state lock."""
        pdir = self._project_dir(pid)
        pdir.mkdir(parents=True, exist_ok=True)
        if _HAS_FILELOCK:
            return FileLock(str(self._lock_file(pid)), timeout=20)
        return self._get_tlock(pid)

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------
    def _read(self, pid: str) -> dict[str, Any]:
        p = self._state_file(pid)
        if not p.exists():
            return {"state": ProjectState.created.value, "history": []}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"state": ProjectState.created.value, "history": []}
        if not isinstance(data, dict) or "state" not in data:
            return {"state": ProjectState.created.value, "history": []}
        return data

    def _write(self, pid: str, data: dict[str, Any]) -> None:
        p = self._state_file(pid)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_state(self, pid: str) -> ProjectState:
        data = self._read(pid)
        try:
            return ProjectState(data.get("state") or ProjectState.created.value)
        except ValueError:
            return ProjectState.created

    def get_history(self, pid: str) -> list[dict[str, Any]]:
        return list(self._read(pid).get("history") or [])

    def get_record(self, pid: str) -> dict[str, Any]:
        data = self._read(pid)
        return {
            "project_id": pid,
            "state": data.get("state") or ProjectState.created.value,
            "history": list(data.get("history") or []),
        }

    def transition(self, pid: str, target: ProjectState | str,
                   *, reason: str = "", actor: str = "") -> ProjectState:
        """Move the project to ``target`` if the transition is legal.

        Self-transitions are idempotent (no error, history unchanged).
        Returns the new state.
        """
        if isinstance(target, str):
            try:
                target = ProjectState(target)
            except ValueError:
                raise StateTransitionError(f"unknown target state: {target!r}")

        lock = self._acquire(pid)
        try:
            with lock:
                data = self._read(pid)
                try:
                    current = ProjectState(data.get("state") or ProjectState.created.value)
                except ValueError:
                    current = ProjectState.created
                if current == target:
                    return current
                allowed = _ALLOWED.get(current, set())
                if target not in allowed:
                    raise StateTransitionError(
                        f"illegal transition {current.value} -> {target.value} "
                        f"(allowed: {sorted(s.value for s in allowed)})"
                    )
                history = list(data.get("history") or [])
                history.append({
                    "from": current.value,
                    "to": target.value,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "reason": reason or "",
                    "actor": actor or "",
                })
                # Cap history so the file does not grow unbounded
                if len(history) > 200:
                    history = history[-200:]
                self._write(pid, {"state": target.value, "history": history})
        except FileLockTimeout as e:
            raise StateTransitionError(f"state lock timeout for {pid}: {e}")

        self.logger.info("project.state_changed", project_id=pid,
                         from_state=current.value, to_state=target.value,
                         reason=reason or None)

        # Fan out WS event (best-effort, must not break the transition)
        try:
            from app.server.ws import publish_sync
            publish_sync(pid, "project.state_changed", {
                "from": current.value, "to": target.value,
                "reason": reason or "",
            })
        except Exception:
            pass
        return target

    def try_transition(self, pid: str, target: ProjectState | str,
                        *, reason: str = "", actor: str = "") -> ProjectState:
        """Best-effort variant — swallow ``StateTransitionError`` and return
        the current state unchanged. Used from routes where blocking the
        request on a state mismatch is more annoying than helpful."""
        try:
            return self.transition(pid, target, reason=reason, actor=actor)
        except StateTransitionError as e:
            self.logger.warning("project.state_skip", project_id=pid,
                                target=str(target), error=str(e))
            return self.get_state(pid)


machine = ProjectStateMachine()
