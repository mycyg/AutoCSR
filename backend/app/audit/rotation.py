"""Audit JSONL rotation helper (M17).

The default audit backend writes one ``<yyyy-mm>.jsonl`` shard per
month. On busy projects an unbounded shard can grow into the hundreds
of megabytes which makes the post-hoc hash-chain verifier slow.

This module rotates a shard to ``<yyyy-mm>.<seq>.jsonl.gz`` once it
crosses :data:`DEFAULT_THRESHOLD_BYTES`. The original .jsonl is then
truncated to zero so subsequent appends continue under the same name.

The hash chain stays intact because :func:`latest_hash` only reads the
*current* shard — the rotated archive is a frozen snapshot and never
re-read by the live append path.
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("autocsr.audit.rotation")


DEFAULT_THRESHOLD_BYTES = 100 * 1024 * 1024  # 100 MiB


_LOCK_GUARD = threading.Lock()
_LOCKS: dict[Path, threading.RLock] = {}


def _flock(p: Path) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(p)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[p] = lk
        return lk


def _next_seq(shard: Path) -> int:
    """Return the next sequence integer for ``shard.gz`` siblings."""
    stem = shard.stem  # e.g. "2026-05"
    parent = shard.parent
    existing = sorted(parent.glob(f"{stem}.*.jsonl.gz"))
    if not existing:
        return 1
    # Format: <yyyy-mm>.<seq>.jsonl.gz
    seqs: list[int] = []
    for f in existing:
        try:
            tail = f.name[len(stem) + 1:]
            seq_s = tail.split(".", 1)[0]
            seqs.append(int(seq_s))
        except (ValueError, IndexError):
            continue
    return (max(seqs) + 1) if seqs else 1


def rotate_if_needed(
    shard_path: Path,
    *,
    threshold_bytes: int = DEFAULT_THRESHOLD_BYTES,
) -> Path | None:
    """If ``shard_path`` exceeds ``threshold_bytes``, gzip-archive it
    and truncate the original. Returns the archive path on rotation,
    None otherwise."""
    try:
        if not shard_path.exists():
            return None
        size = shard_path.stat().st_size
        if size < threshold_bytes:
            return None
    except OSError:
        return None
    with _flock(shard_path):
        # Re-check after acquiring the lock (race)
        try:
            size = shard_path.stat().st_size
        except OSError:
            return None
        if size < threshold_bytes:
            return None
        seq = _next_seq(shard_path)
        archive = shard_path.parent / f"{shard_path.stem}.{seq}.jsonl.gz"
        try:
            with shard_path.open("rb") as src, gzip.open(archive, "wb") as dst:
                shutil.copyfileobj(src, dst)
            # Truncate the live shard so subsequent appends keep going.
            shard_path.write_bytes(b"")
            logger.info(
                "audit.rotation.archived shard=%s -> %s size=%d",
                shard_path.name, archive.name, size,
            )
            return archive
        except OSError as e:
            logger.warning("audit rotation failed: %s", e)
            return None


def maybe_rotate_project_audit(
    project_id: str,
    *,
    ts: datetime | None = None,
    threshold_bytes: int = DEFAULT_THRESHOLD_BYTES,
) -> Path | None:
    """Rotate the current month's shard for one project.

    Cheap to call on every append: the size check is one stat().
    """
    from app.config import data_dir
    ts = ts or datetime.now(timezone.utc)
    shard = data_dir() / "projects" / project_id / "audit" / f"{ts.strftime('%Y-%m')}.jsonl"
    return rotate_if_needed(shard, threshold_bytes=threshold_bytes)


__all__ = [
    "DEFAULT_THRESHOLD_BYTES", "rotate_if_needed",
    "maybe_rotate_project_audit",
]
