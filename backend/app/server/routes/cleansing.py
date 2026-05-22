"""Cleansing routes — proposals lifecycle + apply + rollback + pipeline IO."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.cleansing.auditor import log as audit_log, read_log
from app.cleansing.pipeline_io import (
    export_pipeline as export_yaml, import_pipeline as import_yaml,
    load_proposals, save_proposals,
)
from app.cleansing.proposer import propose as gen_proposals
from app.cleansing.transformer import apply_proposals, list_snapshots, rollback as do_rollback
from app.config import data_dir
from app.ingestion.orchestrator import load_result, load_entries
from app.schemas.cleansing import CleansingProposal
from app.server.ws import publish

router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.get("/projects/{pid}/cleansing/proposals")
async def list_or_generate(
    pid: str,
    file_id: str = Query(...),
    refresh: bool = Query(False),
) -> list[dict[str, Any]]:
    _ensure_project(pid)
    existing = [p for p in load_proposals(pid) if p.file_id == file_id]
    if existing and not refresh:
        return [p.model_dump() for p in existing]
    # Generate from the file's IngestResult + its profiles
    result = load_result(pid, file_id)
    if not result:
        raise HTTPException(status_code=409, detail=f"file {file_id} not ingested yet")
    if not result.profiles:
        return []
    proposals: list[CleansingProposal] = []
    for prof in result.profiles:
        proposals.extend(await gen_proposals(prof, result))
    # Persist alongside any proposals from other files (replace this file's slot)
    keep = [p for p in load_proposals(pid) if p.file_id != file_id]
    save_proposals(pid, keep + proposals)
    return [p.model_dump() for p in proposals]


@router.patch("/projects/{pid}/cleansing/proposals/{proposal_id}")
def update_proposal(
    pid: str, proposal_id: str,
    body: dict = Body(...),
) -> dict[str, Any]:
    _ensure_project(pid)
    items = load_proposals(pid)
    for i, p in enumerate(items):
        if p.id != proposal_id:
            continue
        new_status = body.get("status")
        if new_status:
            if p.mandatory and new_status == "rejected":
                raise HTTPException(status_code=400, detail="mandatory proposal cannot be rejected")
            p.status = new_status
        if "parameters" in body and isinstance(body["parameters"], dict):
            p.parameters = body["parameters"]
            p.status = "edited" if p.status == "pending" else p.status
            p.edited_at = datetime.now(timezone.utc)
        if "target_columns" in body and isinstance(body["target_columns"], list):
            p.target_columns = body["target_columns"]
        items[i] = p
        save_proposals(pid, items)
        audit_log(pid, p.file_id, body.get("status") or "edit",
                  proposal_id=p.id, parameters=p.parameters)
        return p.model_dump()
    raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")


@router.post("/projects/{pid}/cleansing/apply")
async def apply(
    pid: str,
    body: dict = Body(...),
) -> dict[str, Any]:
    _ensure_project(pid)
    file_id = body.get("file_id")
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id required")
    proposals = [p for p in load_proposals(pid) if p.file_id == file_id]
    accepted = [p for p in proposals if p.status in ("accepted", "edited")]
    # Force-include mandatory hash_pii regardless of status to enforce policy
    for p in proposals:
        if p.mandatory and p not in accepted and p.status != "applied":
            accepted.append(p)
    if not accepted:
        return {"ok": False, "reason": "no accepted proposals"}

    # Locate parquet path (prefer ingest result artifacts)
    result = load_result(pid, file_id)
    src_path: Path | None = None
    sheet: str | None = None
    if result:
        # messy_tabular case has parquet:<sheet> keys
        for k, v in result.artifacts.items():
            if k == "parquet":
                src_path = Path(v)
                break
            if k.startswith("parquet:"):
                src_path = Path(v)
                sheet = k.split(":", 1)[1]
                break
    if not src_path or not src_path.exists():
        # fallback: scan raw/<file_id>/
        rdir = data_dir() / "projects" / pid / "raw" / file_id
        for name in ("data.parquet", "data.csv"):
            cand = rdir / name
            if cand.exists():
                src_path = cand
                break
        if src_path is None:
            for cand in rdir.glob("*.parquet"):
                src_path = cand
                break
        if src_path is None:
            for cand in rdir.glob("*.csv"):
                src_path = cand
                break
    if not src_path:
        raise HTTPException(status_code=409, detail="no source parquet/csv for this file")

    await publish(pid, "cleansing.applying", {
        "file_id": file_id, "n_proposals": len(accepted),
    })
    out = await asyncio.to_thread(
        apply_proposals, src_path, accepted,
        project_id=pid, file_id=file_id, sheet=sheet,
    )

    # Mark proposals as applied
    items = load_proposals(pid)
    for i, p in enumerate(items):
        if p in accepted:
            p.status = "applied"
            items[i] = p
    save_proposals(pid, items)

    audit_log(pid, file_id, "apply",
              snapshot_id=out["snapshot_id"],
              rows_before=out["rows_before"], rows_after=out["rows_after"],
              applied=out["applied"], processed_path=out["processed_path"])
    await publish(pid, "cleansing.apply_done", {
        "file_id": file_id, "snapshot_id": out["snapshot_id"],
        "rows_after": out["rows_after"],
    })
    try:
        from app.state import default_machine, ProjectState
        default_machine.try_transition(pid, ProjectState.cleansed,
                                        reason=f"apply {file_id}")
    except Exception:
        pass
    return out


@router.post("/projects/{pid}/cleansing/rollback")
async def rollback(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    snap_id = body.get("snapshot_id")
    if not snap_id:
        raise HTTPException(status_code=400, detail="snapshot_id required")
    out = await asyncio.to_thread(do_rollback, pid, snap_id)
    if out.get("ok"):
        audit_log(pid, body.get("file_id", ""), "rollback", snapshot_id=snap_id)
        await publish(pid, "cleansing.rollback", {"snapshot_id": snap_id})
    return out


@router.get("/projects/{pid}/cleansing/snapshots")
def snapshots(pid: str, file_id: str | None = Query(None)) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [s.model_dump() for s in list_snapshots(pid, file_id)]


@router.get("/projects/{pid}/cleansing/pipeline")
def get_pipeline(
    pid: str, file_id: str | None = Query(None),
) -> dict[str, Any]:
    _ensure_project(pid)
    yaml_text = export_yaml(pid, file_id=file_id)
    return {"yaml": yaml_text}


@router.post("/projects/{pid}/cleansing/pipeline")
def post_pipeline(
    pid: str, body: dict = Body(...),
) -> dict[str, Any]:
    _ensure_project(pid)
    yaml_text = body.get("yaml")
    target_file_id = body.get("target_file_id")
    if not yaml_text or not target_file_id:
        raise HTTPException(status_code=400, detail="yaml and target_file_id required")
    imported = import_yaml(pid, yaml_text, target_file_id=target_file_id)
    return {"imported": len(imported)}


@router.get("/projects/{pid}/cleansing/audit")
def audit(pid: str, limit: int = Query(200)) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return [e.model_dump() for e in read_log(pid, limit=limit)]


@router.get("/projects/{pid}/cleansing/preview")
def preview(pid: str, file_id: str = Query(...), n: int = Query(50)) -> dict[str, Any]:
    _ensure_project(pid)
    import pandas as pd
    candidates: list[Path] = []
    proc_dir = data_dir() / "projects" / pid / "processed"
    for ext in ("parquet", "csv"):
        candidates.extend(proc_dir.glob(f"{file_id}*.{ext}"))
    if not candidates:
        raise HTTPException(status_code=404, detail="no processed file yet")
    target = candidates[0]
    if target.suffix == ".parquet":
        df = pd.read_parquet(target)
    else:
        df = pd.read_csv(target, dtype=str, encoding_errors="replace")
    df = df.head(n)
    return {
        "file_id": file_id, "path": str(target),
        "columns": [str(c) for c in df.columns],
        "rows": df.fillna("").astype(str).values.tolist(),
        "n_rows_returned": int(df.shape[0]),
    }
