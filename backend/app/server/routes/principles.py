"""Read-only principle endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.principles import list_principles, load_principle

router = APIRouter(tags=["admin"])


@router.get("/principles")
def all_principles() -> list[dict[str, Any]]:
    return [p.model_dump() for p in list_principles()]


@router.get("/principles/{pid}")
def principle(pid: str) -> dict[str, Any]:
    try:
        p = load_principle(pid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"principle {pid} not found")
    return p.model_dump()
