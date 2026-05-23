"""Append-only audit log with SHA-256 hash chain (M15).

Default backend: monthly-sharded JSONL files under
``data/projects/<pid>/audit/<yyyy-mm>.jsonl``. Each call to
:func:`append_event` re-reads the latest event hash of the current shard
under a per-project lock, computes the new ``curr_event_hash``, and
appends the line. ``verify_chain`` walks every shard in order and
re-derives every hash.

Pluggable: callers needing S3 Object Lock / IPFS / SQS only need to
subclass :class:`AuditBackend` and ``set_backend`` at startup.
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.schemas import AuditEvent, ChainVerifyResult
from app.config import data_dir

# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

GENESIS_HASH = ""


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _event_hash(prev_hash: str, body_payload: dict[str, Any]) -> str:
    h = hashlib.sha256()
    h.update((prev_hash or "").encode("utf-8"))
    h.update(b"\n")
    h.update(_canonical_json(body_payload).encode("utf-8"))
    return h.hexdigest()


def _body_payload(event: AuditEvent) -> dict[str, Any]:
    """The fields that are covered by the hash chain (everything except the
    two chain-hash fields themselves)."""
    return {
        "id": event.id,
        "ts": event.ts.isoformat() if hasattr(event.ts, "isoformat") else str(event.ts),
        "actor": event.actor,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "before_hash": event.before_hash,
        "after_hash": event.after_hash,
        "reason": event.reason,
        "ip": event.ip,
        "extra": event.extra or {},
    }


def content_hash(text: str | bytes | None) -> str:
    """Helper used by middleware to populate ``before_hash`` / ``after_hash``."""
    if text is None:
        return ""
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


# ---------------------------------------------------------------------------
# Backend abstraction
# ---------------------------------------------------------------------------

class AuditBackend(ABC):
    @abstractmethod
    def append_event(self, project_id: str, event: AuditEvent) -> AuditEvent: ...

    @abstractmethod
    def read_events(
        self,
        project_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[AuditEvent]: ...

    @abstractmethod
    def latest_hash(self, project_id: str) -> str: ...


_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


class JSONLBackend(AuditBackend):
    """Monthly-sharded JSONL with per-project lock."""

    def _audit_dir(self, pid: str) -> Path:
        p = data_dir() / "projects" / pid / "audit"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _shard_for(self, pid: str, ts: datetime) -> Path:
        return self._audit_dir(pid) / f"{ts.strftime('%Y-%m')}.jsonl"

    def _all_shards(self, pid: str) -> list[Path]:
        if not (data_dir() / "projects" / pid / "audit").exists():
            return []
        return sorted(self._audit_dir(pid).glob("*.jsonl"))

    def latest_hash(self, project_id: str) -> str:
        shards = self._all_shards(project_id)
        if not shards:
            return GENESIS_HASH
        last_shard = shards[-1]
        last = ""
        with last_shard.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = str(d.get("curr_event_hash") or "")
        return last

    def append_event(self, project_id: str, event: AuditEvent) -> AuditEvent:
        with _plock(project_id):
            prev = self.latest_hash(project_id)
            body = _body_payload(event)
            curr = _event_hash(prev, body)
            event = event.model_copy(update={
                "prev_event_hash": prev,
                "curr_event_hash": curr,
            })
            shard = self._shard_for(project_id, event.ts)
            with shard.open("a", encoding="utf-8") as f:
                f.write(json.dumps(json.loads(event.model_dump_json()),
                                    ensure_ascii=False) + "\n")
        return event

    def read_events(
        self,
        project_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[AuditEvent]:
        out: list[AuditEvent] = []
        for shard in self._all_shards(project_id):
            with shard.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = AuditEvent.model_validate_json(line)
                    except Exception:
                        continue
                    if start and ev.ts < start:
                        continue
                    if end and ev.ts > end:
                        continue
                    out.append(ev)
        if limit is not None and limit > 0:
            out = out[-limit:]
        return out


# ---------------------------------------------------------------------------
# Module-level backend registry
# ---------------------------------------------------------------------------

_BACKEND: AuditBackend = JSONLBackend()


def get_backend() -> AuditBackend:
    return _BACKEND


def set_backend(backend: AuditBackend) -> None:
    global _BACKEND
    _BACKEND = backend


# ---------------------------------------------------------------------------
# High-level helpers (used by middleware + routes)
# ---------------------------------------------------------------------------

def make_event(
    *,
    actor: str = "",
    action: str = "",
    resource_type: str = "",
    resource_id: str = "",
    before_hash: str | None = None,
    after_hash: str | None = None,
    reason: str | None = None,
    ip: str | None = None,
    extra: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4().hex[:16],
        ts=datetime.now(timezone.utc),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_hash=before_hash,
        after_hash=after_hash,
        reason=reason,
        ip=ip,
        extra=extra or {},
    )


def append_event(project_id: str, event: AuditEvent) -> AuditEvent:
    saved = _BACKEND.append_event(project_id, event)
    # Best-effort WS notify; never break the underlying mutation.
    try:
        from app.server.ws import publish_sync
        publish_sync(project_id, "audit.event_appended", {
            "id": saved.id,
            "action": saved.action,
            "actor": saved.actor,
            "resource_type": saved.resource_type,
            "resource_id": saved.resource_id,
            "ts": saved.ts.isoformat(),
        })
    except Exception:
        pass
    return saved


def read_events(
    project_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> list[AuditEvent]:
    return _BACKEND.read_events(project_id, start=start, end=end, limit=limit)


def verify_chain(
    project_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ChainVerifyResult:
    events = read_events(project_id, start=start, end=end)
    if not events:
        return ChainVerifyResult(verified=True, total=0)
    # When start was supplied we cannot re-derive the very first event's
    # prev_hash, so we accept whatever prev value the first event carries
    # as a baseline.
    prev = events[0].prev_event_hash
    for ev in events:
        body = _body_payload(ev)
        expected = _event_hash(prev, body)
        if ev.prev_event_hash != prev:
            return ChainVerifyResult(verified=False, total=len(events),
                                     broken_at=ev.id,
                                     error="prev_hash_mismatch")
        if ev.curr_event_hash != expected:
            return ChainVerifyResult(verified=False, total=len(events),
                                     broken_at=ev.id,
                                     error="curr_hash_mismatch")
        prev = ev.curr_event_hash
    return ChainVerifyResult(verified=True, total=len(events))
