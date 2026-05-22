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


def _safe_node(node_id: str) -> str:
    return node_id.replace("/", "_")


def _version_path(pid: str, node_id: str, version: int) -> Path:
    return _chapters_dir(pid) / f"{_safe_node(node_id)}_v{int(version)}.json"


def list_versions(pid: str, node_id: str) -> list[int]:
    """Return ascending list of saved version numbers for one section."""
    d = _chapters_dir(pid)
    prefix = f"{_safe_node(node_id)}_v"
    out: list[int] = []
    for f in d.glob(f"{prefix}*.json"):
        stem = f.stem  # e.g. "11.2.3_v7"
        try:
            ver = int(stem.rsplit("_v", 1)[-1])
        except ValueError:
            continue
        out.append(ver)
    return sorted(out)


def load_version(pid: str, node_id: str, version: int) -> SectionDraft | None:
    p = _version_path(pid, node_id, version)
    if not p.exists():
        return None
    try:
        return SectionDraft.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def snapshot_draft(pid: str, draft: SectionDraft) -> int:
    """Persist a versioned snapshot of the draft.

    Returns the version number assigned. Versions start at 1 and grow
    monotonically per section. The "current" draft file (without ``_v*``
    suffix) is always kept in sync by :func:`save_draft`.
    """
    versions = list_versions(pid, draft.node_id)
    next_ver = (versions[-1] + 1) if versions else 1
    p = _version_path(pid, draft.node_id, next_ver)
    payload = json.loads(draft.model_dump_json())
    payload.setdefault("_meta", {})["version"] = next_ver
    with _lock(pid):
        p.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return next_ver


def restore_version(pid: str, node_id: str, version: int) -> SectionDraft | None:
    """Restore a snapshot to be the current draft (also creates a new snapshot
    of the restored content so version history is monotonic)."""
    src = load_version(pid, node_id, version)
    if src is None:
        return None
    # Re-save as current; bump warnings to mark provenance
    warnings = list(src.warnings or [])
    warnings.append(f"restored_from_v{int(version)}")
    restored = src.model_copy(update={"warnings": warnings})
    save_draft(pid, restored)
    snapshot_draft(pid, restored)
    return restored


# ---------------------------------------------------------------------------
# Chat history persistence
# ---------------------------------------------------------------------------

def _chats_dir(pid: str) -> Path:
    p = _proj_dir(pid) / "chats"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _chat_path(pid: str, node_id: str) -> Path:
    return _chats_dir(pid) / f"{_safe_node(node_id)}.jsonl"


def append_chat_message(pid: str, node_id: str, message_payload: dict[str, Any]) -> None:
    p = _chat_path(pid, node_id)
    line = json.dumps(message_payload, ensure_ascii=False, default=str)
    with _lock(pid):
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_chat_history(pid: str, node_id: str) -> list[dict[str, Any]]:
    p = _chat_path(pid, node_id)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def delete_chat_message(pid: str, node_id: str, message_id: str) -> bool:
    p = _chat_path(pid, node_id)
    if not p.exists():
        return False
    items = load_chat_history(pid, node_id)
    new_items = [m for m in items if m.get("id") != message_id]
    if len(new_items) == len(items):
        return False
    with _lock(pid):
        p.write_text(
            "\n".join(json.dumps(m, ensure_ascii=False, default=str) for m in new_items) + ("\n" if new_items else ""),
            encoding="utf-8",
        )
    return True


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
