"""DOCX export routes (M5 + M13 advanced templates).

  POST   /api/projects/{pid}/export/docx
  GET    /api/projects/{pid}/export/docx/{filename}
  DELETE /api/projects/{pid}/export/docx/{filename}
  GET    /api/projects/{pid}/exports

  M13:
  GET    /api/projects/{pid}/export/template_config
  PATCH  /api/projects/{pid}/export/template_config
  GET    /api/projects/{pid}/export/templates
  POST   /api/projects/{pid}/export/template_upload    (multipart .docx)
  GET    /api/export/presets
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import data_dir
from app.export.docx_builder import (
    build_docx, delete_export, export_path, list_exports,
)
from app.export.template_engine import (
    DocxTemplateConfig, apply_patch as apply_cfg_patch, get_preset,
    load_config as load_cfg, preset_names, save_config as save_cfg,
)
from app.export.template_uploader import (
    list_templates as list_uploaded_templates, store_uploaded,
)
from app.server.ws import publish

logger = logging.getLogger("autocsr.export.routes")
router = APIRouter(tags=["export"])


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
    # Optional one-off template_config override (otherwise persisted config used)
    template_override = opts.get("template_config")
    cfg: DocxTemplateConfig | None = None
    if template_override:
        try:
            cfg = DocxTemplateConfig(**template_override)
        except Exception:
            cfg = None

    loop = asyncio.get_running_loop()
    started_at = datetime.now().isoformat(timespec="seconds")
    await publish(pid, "export.start", {"started_at": started_at})

    def _progress(msg: str) -> None:
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
                template_config=cfg,
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
        try:
            from app.state import default_machine, ProjectState
            default_machine.try_transition(pid, ProjectState.exported,
                                            reason=f"docx {result['filename']}")
        except Exception:
            pass
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


# ---------------------------------------------------------------------------
# M13 — template config + uploads + presets
# ---------------------------------------------------------------------------


@router.get("/projects/{pid}/export/template_config")
def get_template_config(pid: str) -> dict[str, Any]:
    _ensure_project(pid)
    cfg = load_cfg(pid)
    return cfg.model_dump()


@router.patch("/projects/{pid}/export/template_config")
def patch_template_config(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    # Two shapes are accepted:
    #   - {"preset": "pharma"} → load preset wholesale (preserves any custom_template_id)
    #   - any subset of fields → deep-merge patch
    preset_name = body.get("preset_apply") or body.get("__apply_preset__")
    if preset_name:
        cfg = get_preset(preset_name)
        save_cfg(pid, cfg)
        return cfg.model_dump()
    cfg = apply_cfg_patch(pid, body)
    return cfg.model_dump()


@router.get("/projects/{pid}/export/templates")
def list_project_templates(pid: str) -> list[dict[str, Any]]:
    _ensure_project(pid)
    return list_uploaded_templates(pid)


@router.post("/projects/{pid}/export/template_upload")
async def upload_template(pid: str, file: UploadFile = File(...)) -> dict[str, Any]:
    _ensure_project(pid)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")
    rec = store_uploaded(pid, file.filename or "template.docx", raw)
    return rec


@router.get("/export/presets")
def list_presets() -> list[dict[str, Any]]:
    return [get_preset(n).model_dump() | {"id": n} for n in preset_names()]
