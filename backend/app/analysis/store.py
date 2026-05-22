"""StatBlock persistence layer.

Each project gets:
    data/projects/<pid>/stats/<stat_id>.json     — full block
    data/projects/<pid>/stats/index.json         — list of StatBlockSummary
Mirrors each saved block into the corpus as a `stat` block so writer agents
can grep / search them alongside literature.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.corpus.index import Block, add_block, drop_block, make_ref
from app.schemas.stats import AnalysisType, StatBlock, StatBlockSummary

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _LOCKS_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _stats_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "stats"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path(pid: str) -> Path:
    return _stats_dir(pid) / "index.json"


def _block_path(pid: str, stat_id: str) -> Path:
    return _stats_dir(pid) / f"{stat_id}.json"


def _load_index(pid: str) -> list[dict[str, Any]]:
    p = _index_path(pid)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_index(pid: str, items: list[dict[str, Any]]) -> None:
    _index_path(pid).write_text(
        json.dumps(items, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _summary_dict(block: StatBlock) -> dict[str, Any]:
    n_rows = None
    n_cols = None
    rj = block.result_json or {}
    if isinstance(rj.get("n_subjects_total"), int):
        n_rows = rj["n_subjects_total"]
    elif isinstance(rj.get("n"), (int, list)):
        n_rows = rj["n"] if isinstance(rj["n"], int) else sum(int(x) for x in rj["n"])
    summary = StatBlockSummary(
        id=block.id, project_id=block.project_id,
        analysis_type=block.analysis_type, title=block.title,
        source_files=block.source_files, created_at=block.created_at,
        ref_code=block.ref_code, n_rows=n_rows, n_cols=n_cols,
    )
    return json.loads(summary.model_dump_json())


def save(project_id: str, block: StatBlock) -> StatBlock:
    """Persist a StatBlock + register it in the project corpus."""
    block = block.model_copy(update={"project_id": project_id})

    # Mirror into corpus first so we have the bid to embed in ref_code
    corpus_text = f"{block.title}\n\n{block.markdown_table}".strip()
    corpus_block = Block(
        id=block.id,                         # reuse stat id as corpus block id
        project_id=project_id,
        type="stat",
        page=1, col=1, para=1,
        text=corpus_text,
        meta={
            "analysis_type": block.analysis_type,
            "stat_id": block.id,
            "title": block.title,
        },
    )
    bid = add_block(project_id, corpus_block)
    ref = make_ref(corpus_block.model_copy(update={"id": bid}))
    block = block.model_copy(update={"ref_code": ref})

    with _lock(project_id):
        _block_path(project_id, block.id).write_text(
            json.dumps(json.loads(block.model_dump_json()),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        idx = _load_index(project_id)
        idx = [x for x in idx if x.get("id") != block.id]   # dedupe on resave
        idx.append(_summary_dict(block))
        _save_index(project_id, idx)
    return block


def list_blocks(project_id: str, analysis_type: AnalysisType | None = None) -> list[dict[str, Any]]:
    with _lock(project_id):
        idx = _load_index(project_id)
    if analysis_type:
        idx = [x for x in idx if x.get("analysis_type") == analysis_type]
    # Sort newest first
    def _ts(x: dict[str, Any]) -> str:
        return str(x.get("created_at") or "")
    return sorted(idx, key=_ts, reverse=True)


def get(project_id: str, stat_id: str) -> StatBlock | None:
    p = _block_path(project_id, stat_id)
    if not p.exists():
        return None
    try:
        return StatBlock.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete(project_id: str, stat_id: str) -> bool:
    with _lock(project_id):
        idx = _load_index(project_id)
        new = [x for x in idx if x.get("id") != stat_id]
        if len(new) == len(idx):
            return False
        _save_index(project_id, new)
        p = _block_path(project_id, stat_id)
        if p.exists():
            p.unlink()
    # Drop from corpus too
    drop_block(project_id, stat_id)
    return True


def search(
    project_id: str,
    analysis_type: AnalysisType | None = None,
    title_query: str | None = None,
) -> list[dict[str, Any]]:
    items = list_blocks(project_id, analysis_type)
    if title_query:
        q = title_query.lower()
        items = [x for x in items if q in str(x.get("title", "")).lower()]
    return items
