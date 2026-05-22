"""Outline routes — build, get, patch, child crud, version history, restore."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from app.config import data_dir
from app.outline.builder import build as build_outline
from app.outline.store import (
    add_child, delete_node, list_versions, load as load_outline,
    restore_version, update_node,
)
from app.server.ws import publish

logger = logging.getLogger("autocsr.outline.routes")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/outline/build")
async def build_endpoint(pid: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    principle_id = body.get("principle_id")
    if not principle_id:
        raise HTTPException(status_code=400, detail="principle_id required")
    await publish(pid, "outline.build_start", {"principle_id": principle_id})

    async def _runner() -> None:
        try:
            outline = await build_outline(pid, principle_id)
            await publish(pid, "outline.build_done", {
                "principle_id": principle_id,
                "version": outline.version,
                "n_nodes": len(outline.walk()),
            })
        except Exception as e:
            logger.exception("outline.build failed")
            await publish(pid, "outline.error", {"error": str(e)})

    task = asyncio.create_task(_runner())
    try:
        # Wait up to 5min for the build (LLM enrichment can be slow with many sections)
        await asyncio.wait_for(asyncio.shield(task), timeout=300)
    except asyncio.TimeoutError:
        return {"started": True, "status": "running"}
    outline = load_outline(pid)
    return {"started": True, "status": "done",
            "version": outline.version if outline else None,
            "n_nodes": len(outline.walk()) if outline else 0}


@router.get("/projects/{pid}/outline")
def get_outline(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    outline = load_outline(pid)
    if not outline:
        raise HTTPException(status_code=404, detail="outline not built yet")
    return outline.model_dump()


@router.patch("/projects/{pid}/outline/nodes/{node_id}")
def patch_node(pid: str, node_id: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    node = update_node(pid, node_id, body)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump()


@router.post("/projects/{pid}/outline/nodes/{parent_id}/children")
def add_child_endpoint(pid: str, parent_id: str, body: dict = Body(...)) -> dict[str, Any]:
    _ensure_project(pid)
    title = body.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    node = add_child(
        pid, parent_id, title,
        notes=body.get("notes", ""),
        stat_hints=body.get("stat_hints"),
    )
    if node is None:
        raise HTTPException(status_code=404, detail="parent not found")
    return node.model_dump()


@router.delete("/projects/{pid}/outline/nodes/{node_id}")
def delete_node_endpoint(pid: str, node_id: str) -> dict[str, bool]:
    _ensure_project(pid)
    return {"ok": delete_node(pid, node_id)}


@router.get("/projects/{pid}/outline/versions")
def versions(pid: str) -> list[int]:
    _ensure_project(pid)
    return list_versions(pid)


@router.post("/projects/{pid}/outline/restore/{version}")
async def restore(pid: str, version: int) -> dict[str, Any]:
    _ensure_project(pid)
    outline = restore_version(pid, version)
    if outline is None:
        raise HTTPException(status_code=404, detail=f"version {version} not found")
    await publish(pid, "outline.restored", {"from": version, "now": outline.version})
    return {"ok": True, "version": outline.version}
