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

  M19 — multi-format export:
  POST   /api/projects/{pid}/export/pdf
  POST   /api/projects/{pid}/export/html
  POST   /api/projects/{pid}/export/pptx
  POST   /api/projects/{pid}/export/md_bundle
  GET    /api/projects/{pid}/export/{format}/{filename}    download file
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


# ---------------------------------------------------------------------------
# M19 — multi-format export (PDF / HTML / PPTX / Markdown bundle)
# ---------------------------------------------------------------------------


def _format_to_media_type(fmt: str) -> str:
    return {
        "pdf": "application/pdf",
        "html": "text/html; charset=utf-8",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "md_bundle": "application/zip",
    }.get(fmt, "application/octet-stream")


async def _run_multi_format(
    pid: str, fmt: str, body: dict[str, Any] | None,
) -> dict[str, Any]:
    """Shared driver for the 4 new exporters. Publishes
    ``export.<fmt>.start/progress/done`` WS events and returns the
    builder result dict on success.
    """
    body = body or {}
    loop = asyncio.get_running_loop()
    await publish(pid, f"export.{fmt}.start",
                  {"started_at": datetime.now().isoformat(timespec="seconds")})

    def _progress(phase: str) -> None:
        try:
            asyncio.run_coroutine_threadsafe(
                publish(pid, f"export.{fmt}.progress", {"phase": phase}),
                loop,
            )
        except Exception:
            pass

    def _build() -> dict[str, Any]:
        try:
            if fmt == "pdf":
                from app.export.pdf_builder import build_pdf
                res = build_pdf(
                    pid,
                    template_config=body.get("template_config"),
                    include_compliance_note=bool(body.get("include_compliance_note", True)),
                    include_appendix_cleansing=bool(body.get("include_appendix_cleansing", True)),
                    include_appendix_analysis=bool(body.get("include_appendix_analysis", True)),
                    progress_cb=_progress,
                )
                payload = {
                    "ok": True, "filename": res.filename,
                    "size_bytes": res.size_bytes,
                    "n_sections": res.n_sections,
                    "n_citations": res.n_citations,
                    "generated_at": res.generated_at,
                }
            elif fmt == "html":
                from app.export.html_builder import build_html
                res = build_html(
                    pid,
                    include_compliance_note=bool(body.get("include_compliance_note", True)),
                    progress_cb=_progress,
                )
                payload = {
                    "ok": True, "filename": res.filename,
                    "size_bytes": res.size_bytes,
                    "n_sections": res.n_sections,
                    "n_charts": res.n_charts,
                    "n_citations": res.n_citations,
                    "generated_at": res.generated_at,
                }
            elif fmt == "pptx":
                from app.export.pptx_builder import build_pptx
                res = build_pptx(pid, progress_cb=_progress)
                payload = {
                    "ok": True, "filename": res.filename,
                    "size_bytes": res.size_bytes,
                    "n_slides": res.n_slides,
                    "generated_at": res.generated_at,
                }
            elif fmt == "md_bundle":
                from app.export.markdown_bundle import build_markdown_bundle
                res = build_markdown_bundle(pid, progress_cb=_progress)
                payload = {
                    "ok": True, "filename": res.filename,
                    "size_bytes": res.size_bytes,
                    "n_files": res.n_files,
                    "generated_at": res.generated_at,
                }
            else:
                payload = {"ok": False, "error": f"unknown format: {fmt}"}
            # Index alongside docx so /exports lists every format
            if payload.get("ok"):
                from app.export.docx_builder import _index_export
                from pathlib import Path
                from app.config import data_dir
                path = data_dir() / "projects" / pid / "exports" / payload["filename"]
                _index_export(pid, path, n_sections=payload.get("n_sections", 0),
                              n_citations=payload.get("n_citations", 0))
            return payload
        except Exception as e:  # noqa: BLE001
            logger.exception("export.%s failed", fmt)
            return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}

    result = await asyncio.to_thread(_build)
    if result.get("ok"):
        await publish(pid, f"export.{fmt}.done", {
            k: v for k, v in result.items() if k != "ok"
        })
    else:
        await publish(pid, f"export.{fmt}.error", {"error": result.get("error")})
        raise HTTPException(status_code=500, detail=result.get("error") or f"{fmt} build failed")
    return result


@router.post("/projects/{pid}/export/pdf")
async def export_pdf_endpoint(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    return await _run_multi_format(pid, "pdf", body)


@router.post("/projects/{pid}/export/html")
async def export_html_endpoint(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    return await _run_multi_format(pid, "html", body)


@router.post("/projects/{pid}/export/pptx")
async def export_pptx_endpoint(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    return await _run_multi_format(pid, "pptx", body)


@router.post("/projects/{pid}/export/md_bundle")
async def export_md_bundle_endpoint(pid: str, body: dict = Body(default_factory=dict)) -> dict[str, Any]:
    _ensure_project(pid)
    return await _run_multi_format(pid, "md_bundle", body)


@router.get("/projects/{pid}/export/file/{filename}")
def download_any_export(pid: str, filename: str):
    """Generic download for the new formats. The docx route still exists at
    /export/docx/{filename} for backwards compatibility."""
    _ensure_project(pid)
    from pathlib import Path
    base = data_dir() / "projects" / pid / "exports"
    candidate = base / filename
    try:
        if candidate.resolve().parent != base.resolve():
            raise HTTPException(status_code=400, detail="invalid filename")
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid filename") from e
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"export {filename} not found")
    suffix = candidate.suffix.lower().lstrip(".")
    media = _format_to_media_type(
        "md_bundle" if filename.endswith(".md.zip")
        else "pdf" if suffix == "pdf"
        else "html" if suffix == "html"
        else "pptx" if suffix == "pptx"
        else suffix,
    )
    return FileResponse(path=str(candidate), filename=filename, media_type=media)


# Register arq + inmemory handler bridges for the new formats so
# settings.queue.backend='arq' can route them. (Handlers in
# queue/arq_app.py mirror these; inmemory enqueue picks these up.)
def _register_export_handlers() -> None:
    from app.queue.runtime import register_handler

    async def _h_pdf(*, project_id: str, template_config: dict | None = None) -> dict:
        from app.export.pdf_builder import build_pdf
        r = build_pdf(project_id, template_config=template_config)
        return {"ok": True, "filename": r.filename, "size_bytes": r.size_bytes}

    async def _h_html(*, project_id: str) -> dict:
        from app.export.html_builder import build_html
        r = build_html(project_id)
        return {"ok": True, "filename": r.filename, "size_bytes": r.size_bytes}

    async def _h_pptx(*, project_id: str) -> dict:
        from app.export.pptx_builder import build_pptx
        r = build_pptx(project_id)
        return {"ok": True, "filename": r.filename, "size_bytes": r.size_bytes,
                "n_slides": r.n_slides}

    async def _h_md(*, project_id: str) -> dict:
        from app.export.markdown_bundle import build_markdown_bundle
        r = build_markdown_bundle(project_id)
        return {"ok": True, "filename": r.filename, "size_bytes": r.size_bytes,
                "n_files": r.n_files}

    register_handler("export_pdf", _h_pdf)
    register_handler("export_html", _h_html)
    register_handler("export_pptx", _h_pptx)
    register_handler("export_md_bundle", _h_md)


_register_export_handlers()
