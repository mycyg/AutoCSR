"""DOCX export routes (M5).

  POST /api/projects/{pid}/export/docx
  GET  /api/projects/{pid}/export/docx/{filename}
  DELETE /api/projects/{pid}/export/docx/{filename}
  GET  /api/projects/{pid}/exports
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from app.config import data_dir
from app.export.docx_builder import (
    build_docx, delete_export, export_path, list_exports,
)
from app.server.ws import publish

logger = logging.getLogger("autocsr.export.routes")
router = APIRouter()


def _ensure_project(pid: str) -> None:
    if not (data_dir() / "projects" / pid).exists():
        raise HTTPException(status_code=404, detail=f"project {pid} not found")


@router.post("/projects/{pid}/export/docx")
async def export_docx_endpoint(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    opts = dict(body or {})
    include_compliance = bool(opts.get("include_compliance_note", True))
    include_toc = bool(opts.get("include_toc", True))
    include_appendix_cleansing = bool(opts.get("include_appendix_cleansing", True))
    include_appendix_analysis = bool(opts.get("include_appendix_analysis", True))

    loop = asyncio.get_running_loop()
    started_at = datetime.now().isoformat(timespec="seconds")
    await publish(pid, "export.start", {"started_at": started_at})

    def _progress(msg: str) -> None:
        # Bridge sync->async safely
        try:
            asyncio.run_coroutine_threadsafe(
                publish(pid, "export.progress", {"phase": msg}), loop,
            )
        except Exception:
            pass

    def _run() -> dict[str, Any]:
        try:
            res = build_docx(
                pid,
                include_appendix_cleansing=include_appendix_cleansing,
                include_appendix_analysis=include_appendix_analysis,
                include_compliance_note=include_compliance,
                include_toc=include_toc,
                progress_cb=_progress,
            )
            return {
                "ok": True,
                "filename": res.filename,
                "size_bytes": res.size_bytes,
                "n_sections": res.n_sections,
                "n_citations": res.n_citations,
                "generated_at": res.generated_at,
            }
        except Exception as e:  # noqa: BLE001
            logger.exception("docx build failed")
            return {"ok": False, "error": str(e)[:300]}

    result = await asyncio.to_thread(_run)
    if result.get("ok"):
        await publish(pid, "export.done", {
            "filename": result["filename"],
            "size_bytes": result["size_bytes"],
            "n_sections": result["n_sections"],
            "n_citations": result["n_citations"],
        })
    else:
        await publish(pid, "export.error", {"error": result.get("error")})
        raise HTTPException(status_code=500, detail=result.get("error") or "docx build failed")
    return result


@router.get("/projects/{pid}/exports")
def list_exports_endpoint(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return list_exports(pid)


@router.get("/projects/{pid}/export/docx/{filename}")
def download_export(pid: str, filename: str):
    _ensure_project(pid)
    p = export_path(pid, filename)
    if p is None:
        raise HTTPException(status_code=404, detail=f"export {filename} not found")
    return FileResponse(
        path=str(p),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/projects/{pid}/export/docx/{filename}")
def delete_export_endpoint(pid: str, filename: str) -> dict[str, bool]:
    _ensure_project(pid)
    return {"ok": delete_export(pid, filename)}
