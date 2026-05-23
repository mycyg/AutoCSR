"""Corpus search endpoint."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.config import data_dir
from app.corpus.index import search, fetch_ref, list_blocks

router = APIRouter(tags=["admin"])


@router.post("/projects/{pid}/corpus/search")
def corpus_search(pid: str, body: dict = Body(...)) -> list[dict[str, Any]]:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")
    query = body.get("query") or ""
    types = body.get("types")
    top_k = int(body.get("top_k") or 10)
    hits = search(pid, query, types=types, top_k=top_k)
    return [h.model_dump() for h in hits]


@router.get("/projects/{pid}/corpus/fetch")
def corpus_fetch(pid: str, ref_code: str) -> dict[str, Any]:
    block = fetch_ref(pid, ref_code)
    if not block:
        raise HTTPException(status_code=404, detail=f"ref not found: {ref_code}")
    return block.model_dump()


@router.get("/projects/{pid}/corpus/blocks")
def corpus_blocks(pid: str, type: str | None = None) -> list[dict[str, Any]]:
    return list_blocks(pid, type=type)  # type: ignore[arg-type]
