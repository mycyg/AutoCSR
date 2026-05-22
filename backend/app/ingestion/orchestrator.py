"""Orchestrates Router + Workers for all uploaded but un-ingested files of a project.

State is persisted at <data>/projects/<pid>/raw/_index.json (a list of FileEntry).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir, settings
from app.ingestion.router import route
from app.ingestion.workers import dispatch
from app.schemas.ingest import FileEntry, IngestResult
from app.server.ws import publish

logger = logging.getLogger("autocsr.ingest")

_LOCK = threading.RLock()
_BG_TASKS: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# FileEntry persistence (single JSON list per project)
# ---------------------------------------------------------------------------

def _index_path(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p / "_index.json"


def load_entries(project_id: str) -> list[FileEntry]:
    p = _index_path(project_id)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out: list[FileEntry] = []
    for r in raw if isinstance(raw, list) else []:
        try:
            out.append(FileEntry.model_validate(r))
        except Exception:
            continue
    return out


def save_entries(project_id: str, entries: list[FileEntry]) -> None:
    p = _index_path(project_id)
    p.write_text(
        json.dumps([json.loads(e.model_dump_json()) for e in entries],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_entry(project_id: str, entry: FileEntry) -> None:
    with _LOCK:
        items = load_entries(project_id)
        items.append(entry)
        save_entries(project_id, items)


def update_entry(project_id: str, file_id: str, **fields: Any) -> FileEntry | None:
    with _LOCK:
        items = load_entries(project_id)
        for i, e in enumerate(items):
            if e.file_id == file_id:
                merged = e.model_dump()
                merged.update(fields)
                new = FileEntry.model_validate(merged)
                items[i] = new
                save_entries(project_id, items)
                return new
    return None


# ---------------------------------------------------------------------------
# IngestResult persistence
# ---------------------------------------------------------------------------

def _result_path(project_id: str, file_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "raw" / file_id
    p.mkdir(parents=True, exist_ok=True)
    return p / "_ingest_result.json"


def save_result(result: IngestResult) -> None:
    _result_path(result.project_id, result.file_id).write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )


def load_result(project_id: str, file_id: str) -> IngestResult | None:
    p = _result_path(project_id, file_id)
    if not p.exists():
        return None
    try:
        return IngestResult.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

async def _process_one(entry: FileEntry, sem: asyncio.Semaphore) -> IngestResult | None:
    pid = entry.project_id
    fid = entry.file_id
    async with sem:
        # 1. Route
        update_entry(pid, fid, status="routing")
        try:
            decision = await route(entry.stored_path)
        except Exception as e:
            update_entry(pid, fid, status="error", error=f"router: {e}")
            await publish(pid, "worker.error", {"file_id": fid, "error": str(e)})
            return None
        update_entry(
            pid, fid,
            ingest_type=decision.ingest_type,
            ingest_confidence=decision.confidence,
            needs_user_confirm=decision.confidence < 0.6,
            status="running",
        )
        await publish(pid, "router.file_classified", {
            "file_id": fid, "ingest_type": decision.ingest_type,
            "confidence": decision.confidence, "reason": decision.reason,
        })
        # 2. Worker dispatch
        await publish(pid, "worker.start", {
            "file_id": fid, "ingest_type": decision.ingest_type,
        })
        try:
            result = await dispatch(decision.ingest_type, entry.stored_path, pid, fid)
        except Exception as e:
            logger.exception("worker failed: %s", e)
            update_entry(pid, fid, status="error", error=str(e))
            await publish(pid, "worker.error", {"file_id": fid, "error": str(e)})
            return None
        save_result(result)
        if result.error:
            update_entry(pid, fid, status="error", error=result.error)
            await publish(pid, "worker.error", {"file_id": fid, "error": result.error})
        else:
            update_entry(pid, fid, status="done")
            await publish(pid, "worker.done", {
                "file_id": fid, "ingest_type": result.ingest_type,
                "artifacts": list(result.artifacts.keys()),
                "notes": result.notes,
                "needs_review": result.needs_review,
            })
        return result


async def ingest_all(project_id: str) -> list[IngestResult]:
    entries = load_entries(project_id)
    todo = [e for e in entries if e.status in ("uploaded", "error")]
    if not todo:
        return []
    await publish(project_id, "router.start", {"n_files": len(todo)})
    max_par = int(settings().get("pipeline", {}).get("max_parallel_ingest_workers", 4))
    sem = asyncio.Semaphore(max(1, max_par))
    results = await asyncio.gather(*(_process_one(e, sem) for e in todo))
    await publish(project_id, "router.all_done", {"n_processed": len(results)})
    return [r for r in results if r is not None]


def kick_off(project_id: str) -> None:
    """Fire-and-forget background ingestion. Idempotent — repeated calls for the
    same project before the previous run finishes are no-ops."""
    if project_id in _BG_TASKS and not _BG_TASKS[project_id].done():
        return

    async def _runner() -> None:
        try:
            await ingest_all(project_id)
        except Exception as e:
            logger.exception("ingest_all failed: %s", e)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop — run inline in a worker thread
        def _thread() -> None:
            asyncio.run(_runner())
        threading.Thread(target=_thread, daemon=True).start()
        return
    task = loop.create_task(_runner())
    _BG_TASKS[project_id] = task


def project_status(project_id: str) -> dict[str, Any]:
    entries = load_entries(project_id)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.status] = counts.get(e.status, 0) + 1
    return {
        "project_id": project_id,
        "total": len(entries),
        "by_status": counts,
        "all_done": all(e.status in ("done", "error") for e in entries) if entries else True,
        "entries": [json.loads(e.model_dump_json()) for e in entries],
    }


def stamp_uploaded(project_id: str, file_id: str, filename: str, stored_path: Path,
                   *, mime: str | None = None, size_bytes: int = 0) -> FileEntry:
    entry = FileEntry(
        file_id=file_id, project_id=project_id, filename=filename,
        mime=mime, size_bytes=size_bytes, stored_path=str(stored_path),
        uploaded_at=datetime.now(timezone.utc), status="uploaded",
    )
    append_entry(project_id, entry)
    return entry
