"""Hallucination check routes (M17).

POST /api/projects/{pid}/hallucination_check
    → Scans every persisted SectionDraft and returns the aggregated
      list of HallucinationFinding (each tagged with node_id).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.safety.hallucination_guard import project_scan

router = APIRouter(tags=["safety"])


@router.post("/projects/{pid}/hallucination_check")
def run_hallucination_check(pid: str) -> dict[str, Any]:
    findings = project_scan(pid)
    return {
        "project_id": pid,
        "n_findings": len(findings),
        "findings": [f.model_dump() for f in findings],
    }


@router.get("/projects/{pid}/hallucination_check")
def get_hallucination_check(pid: str) -> dict[str, Any]:
    """Same as POST — convenience GET for read-only clients."""
    return run_hallucination_check(pid)
