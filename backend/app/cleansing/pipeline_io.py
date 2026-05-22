"""Pipeline YAML export / import.

A *pipeline* is the ordered list of proposals already applied (status='applied')
or accepted (status='accepted'). It can be re-applied to a new file with
matching columns.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.config import data_dir
from app.schemas.cleansing import CleansingProposal, PipelineRuleYAML


def _proposals_path(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "cleansing_proposals.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_proposals(project_id: str) -> list[CleansingProposal]:
    p = _proposals_path(project_id)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out: list[CleansingProposal] = []
    for r in raw if isinstance(raw, list) else []:
        try:
            out.append(CleansingProposal.model_validate(r))
        except Exception:
            continue
    return out


def save_proposals(project_id: str, proposals: list[CleansingProposal]) -> None:
    p = _proposals_path(project_id)
    p.write_text(
        json.dumps([json.loads(pr.model_dump_json()) for pr in proposals],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_pipeline(project_id: str, *, file_id: str | None = None,
                    statuses: tuple[str, ...] = ("accepted", "applied", "edited")) -> str:
    items = load_proposals(project_id)
    rules: list[dict[str, Any]] = []
    for p in items:
        if file_id and p.file_id != file_id:
            continue
        if p.status not in statuses:
            continue
        rules.append({
            "type": p.type,
            "target_columns": p.target_columns,
            "parameters": p.parameters,
            "rationale": p.rationale,
        })
    doc = {
        "version": "autocsr.cleansing/1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "file_id": file_id,
        "rules": rules,
    }
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def import_pipeline(project_id: str, yaml_text: str, *, target_file_id: str) -> list[CleansingProposal]:
    """Parse a pipeline YAML and synthesize pending proposals for `target_file_id`."""
    import uuid
    doc = yaml.safe_load(yaml_text) or {}
    rules = doc.get("rules") or []
    out: list[CleansingProposal] = []
    for r in rules:
        try:
            rule = PipelineRuleYAML.model_validate(r)
        except Exception:
            continue
        out.append(CleansingProposal(
            id=uuid.uuid4().hex[:12],
            project_id=project_id, file_id=target_file_id,
            type=rule.type, target_columns=rule.target_columns,
            parameters=rule.parameters, rationale=rule.rationale,
            confidence=0.8, impact_rows=0,
            status="pending", mandatory=(rule.type == "hash_pii"),
            created_at=datetime.now(timezone.utc),
        ))
    existing = load_proposals(project_id)
    save_proposals(project_id, existing + out)
    return out
