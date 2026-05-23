"""Coding dictionary routes — list systems, lookup terms, fetch code info."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.coding import dictionary

router = APIRouter()


@router.get("/coding/systems")
def list_systems() -> list[dict[str, Any]]:
    """Return all known dictionary systems with availability + counts."""
    return dictionary.list_systems()


@router.post("/coding/lookup")
def lookup(body: dict = Body(...)) -> dict[str, Any]:
    """Fuzzy lookup ``term`` against ``system`` (top_k candidates)."""
    system = (body.get("system") or "").strip()
    term = (body.get("term") or "").strip()
    top_k = int(body.get("top_k") or 5)
    language = (body.get("language") or "en").strip()
    if not system or not term:
        raise HTTPException(status_code=400, detail="system + term required")
    cands = dictionary.lookup(system, term, top_k=top_k, language=language)
    return {
        "system": system.upper(),
        "term": term,
        "candidates": [c.model_dump() for c in cands],
    }


@router.post("/coding/lookup_many")
def lookup_many(body: dict = Body(...)) -> dict[str, Any]:
    """Batch lookup for a list of terms (each returns top_k candidates)."""
    system = (body.get("system") or "").strip()
    terms = body.get("terms") or []
    top_k = int(body.get("top_k") or 3)
    if not system or not terms:
        raise HTTPException(status_code=400, detail="system + terms required")
    out = dictionary.lookup_many(system, list(terms), top_k=top_k)
    return {
        "system": system.upper(),
        "results": {k: [c.model_dump() for c in v] for k, v in out.items()},
    }


@router.get("/coding/code/{system}/{code}")
def get_code(system: str, code: str) -> dict[str, Any]:
    info = dictionary.get_code_info(system, code)
    if info is None:
        raise HTTPException(status_code=404, detail=f"code {system}/{code} not found")
    return info.model_dump()


@router.get("/coding/suggest_system")
def suggest_system(column: str = Query(...)) -> dict[str, Any]:
    sys_id = dictionary.suggest_system_for_column(column)
    return {"column": column, "system": sys_id}
