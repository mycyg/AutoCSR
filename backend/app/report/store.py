"""Report draft persistence.

Layout per project:
    data/projects/<pid>/chapters/<node_id>.json   — one SectionDraft per file
    data/projects/<pid>/report.json               — assembled ReportDraft (drafts dict)
    data/projects/<pid>/terminology.json          — bilingual term map (key -> value)
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.schemas.report import ReportDraft, SectionDraft

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(pid: str) -> threading.RLock:
    with _LOCKS_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _proj_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chapters_dir(pid: str) -> Path:
    p = _proj_dir(pid) / "chapters"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _draft_path(pid: str, node_id: str) -> Path:
    # node ids may contain dots; that's fine on Windows/posix
    safe = node_id.replace("/", "_")
    return _chapters_dir(pid) / f"{safe}.json"


def _report_path(pid: str) -> Path:
    return _proj_dir(pid) / "report.json"


def _terminology_path(pid: str) -> Path:
    return _proj_dir(pid) / "terminology.json"


DEFAULT_TERMINOLOGY: dict[str, str] = {
    "study drug": "研究药物",
    "comparator": "对照",
    "primary endpoint": "主要终点",
    "secondary endpoint": "次要终点",
    "adverse event": "不良事件",
    "serious adverse event": "严重不良事件",
    "treatment-emergent adverse event": "治疗紧急不良事件",
    "TEAE": "治疗紧急不良事件",
    "hazard ratio": "风险比",
    "confidence interval": "置信区间",
    "safety set": "安全性集",
    "full analysis set": "全分析集",
    "per-protocol set": "符合方案集",
}


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def save_draft(pid: str, draft: SectionDraft) -> SectionDraft:
    payload = json.loads(draft.model_dump_json())
    with _lock(pid):
        _draft_path(pid, draft.node_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return draft


def load_draft(pid: str, node_id: str) -> SectionDraft | None:
    p = _draft_path(pid, node_id)
    if not p.exists():
        return None
    try:
        return SectionDraft.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_drafts(pid: str) -> list[SectionDraft]:
    out: list[SectionDraft] = []
    d = _chapters_dir(pid)
    for f in sorted(d.glob("*.json")):
        try:
            out.append(SectionDraft.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def delete_draft(pid: str, node_id: str) -> bool:
    p = _draft_path(pid, node_id)
    if p.exists():
        p.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Assembled ReportDraft
# ---------------------------------------------------------------------------

def save_report(report: ReportDraft) -> ReportDraft:
    payload = json.loads(report.model_dump_json())
    with _lock(report.project_id):
        _report_path(report.project_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def load_report(pid: str) -> ReportDraft | None:
    p = _report_path(pid)
    if not p.exists():
        return None
    try:
        return ReportDraft.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def assemble_report(
    pid: str,
    outline_version: int,
    *,
    harmonized: bool = False,
) -> ReportDraft:
    """Aggregate every per-section draft on disk into a single ReportDraft."""
    drafts = list_drafts(pid)
    by_id = {d.node_id: d for d in drafts}
    leaves_done = sum(1 for d in drafts if d.status != "error")
    leaves_errored = sum(1 for d in drafts if d.status == "error")
    total_in = sum(d.llm_meta.tokens_in for d in drafts)
    total_out = sum(d.llm_meta.tokens_out for d in drafts)
    total_words = sum(d.word_count for d in drafts)
    rep = ReportDraft(
        project_id=pid,
        outline_version=outline_version,
        drafts=by_id,
        harmonized=harmonized,
        generated_at=datetime.now(timezone.utc),
        leaves_total=len(drafts),
        leaves_done=leaves_done,
        leaves_errored=leaves_errored,
        total_words=total_words,
    )
    rep.total_tokens.input = total_in
    rep.total_tokens.output = total_out
    return rep


# ---------------------------------------------------------------------------
# Terminology
# ---------------------------------------------------------------------------

def load_terminology(pid: str) -> dict[str, str]:
    p = _terminology_path(pid)
    if not p.exists():
        return dict(DEFAULT_TERMINOLOGY)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return dict(DEFAULT_TERMINOLOGY)


def save_terminology(pid: str, terms: dict[str, str]) -> dict[str, str]:
    cleaned = {str(k).strip(): str(v).strip() for k, v in (terms or {}).items() if str(k).strip()}
    with _lock(pid):
        _terminology_path(pid).write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return cleaned
