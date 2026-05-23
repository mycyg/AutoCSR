"""Per-project blinding state (M15).

When ``blinded=True`` the writer/analyst prompts mask every treatment
arm with ``<arm_a>`` / ``<arm_b>`` / ``<arm_c>`` so reviewers cannot
re-identify groups by reading drafts mid-study. The mapping is derived
once from ``ADSL.TRT01P`` (or ``ARM``) unique values, then persisted
alongside the toggle.

Storage: ``data/projects/<pid>/blinding.json``::

    {"blinded": true, "arm_map": {"TRT_A": "<arm_a>", "Placebo": "<arm_b>"},
     "last_changed_at": "...", "signature_id": "sig_..."}

Toggling ``blinded=False`` requires a signature_id; the route layer is
responsible for refusing the call if no signature accompanies it.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir

logger = logging.getLogger("autocsr.state.blinding")

_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}

# A reasonable default for ADSL column candidates
_ARM_CANDIDATE_COLS = ("TRT01P", "TRT01A", "TRTA", "TRTP", "ARM", "ARMCD")


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


def _path(pid: str) -> Path:
    return data_dir() / "projects" / pid / "blinding.json"


def get(pid: str) -> dict[str, Any]:
    p = _path(pid)
    if not p.exists():
        return {"blinded": False, "arm_map": {}, "last_changed_at": None,
                "signature_id": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return {"blinded": False, "arm_map": {}, "last_changed_at": None,
                    "signature_id": None}
        d.setdefault("arm_map", {})
        d.setdefault("last_changed_at", None)
        d.setdefault("signature_id", None)
        return d
    except json.JSONDecodeError:
        return {"blinded": False, "arm_map": {}, "last_changed_at": None,
                "signature_id": None}


def is_blinded(pid: str) -> bool:
    return bool(get(pid).get("blinded"))


def arm_map(pid: str) -> dict[str, str]:
    return dict(get(pid).get("arm_map") or {})


def set_blinded(pid: str, blinded: bool, *, signature_id: str | None = None,
                arms: list[str] | None = None) -> dict[str, Any]:
    with _plock(pid):
        cur = get(pid)
        if blinded and not (cur.get("arm_map") or {}):
            mapping = _derive_arm_map(pid, arms)
            cur["arm_map"] = mapping
        cur["blinded"] = bool(blinded)
        cur["last_changed_at"] = datetime.now(timezone.utc).isoformat()
        cur["signature_id"] = signature_id
        path = _path(pid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cur, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    # WS broadcast
    try:
        from app.server.ws import publish_sync
        publish_sync(pid, "state.blinding_changed", {
            "blinded": cur["blinded"], "signature_id": signature_id,
        })
    except Exception:
        pass
    return cur


def mask_arms(text: str, mapping: dict[str, str] | None = None,
              pid: str | None = None) -> str:
    """Replace each arm label with its masked placeholder."""
    if not text:
        return text
    if mapping is None and pid is not None:
        mapping = arm_map(pid)
    if not mapping:
        return text
    out = text
    # Longest-first so "Placebo HD" wins before "Placebo".
    for raw, mask in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if not raw:
            continue
        out = out.replace(raw, mask)
    return out


def _derive_arm_map(pid: str, arms: list[str] | None) -> dict[str, str]:
    """Best-effort: scan ADSL processed parquet for an arm column;
    fall back to the caller-supplied list."""
    if arms:
        return _build_map(arms)
    candidates = _collect_arms_from_disk(pid)
    if candidates:
        return _build_map(candidates)
    return {}


def _collect_arms_from_disk(pid: str) -> list[str]:
    pdir = data_dir() / "projects" / pid / "processed"
    if not pdir.exists():
        return []
    try:
        import pandas as pd  # local import — heavy
    except Exception:
        return []
    found: list[str] = []
    for path in pdir.glob("*"):
        if path.suffix.lower() not in (".parquet", ".csv"):
            continue
        try:
            if path.suffix.lower() == ".parquet":
                df = pd.read_parquet(path, columns=None)
            else:
                df = pd.read_csv(path, nrows=2000)
        except Exception:
            continue
        for c in _ARM_CANDIDATE_COLS:
            if c in df.columns:
                vals = [str(v) for v in df[c].dropna().unique().tolist()][:6]
                if vals:
                    found = vals
                    break
        if found:
            break
    return found


def _build_map(arms: list[str]) -> dict[str, str]:
    letters = "abcdefghij"
    out: dict[str, str] = {}
    for i, arm in enumerate(arms[:10]):
        out[str(arm)] = f"<arm_{letters[i]}>"
    return out
