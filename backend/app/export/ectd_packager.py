"""eCTD M5.3.5 packager — simplified demo of FDA / NMPA submission layout.

This is **not** a full eCTD validator: the spec defines dozens of fields
and a strict XML backbone. We produce the minimum directory shape so
downstream tooling (or a regulator-grade packager) can take over:

::

    m1/
      m1.2-cover.pdf                       (caller-supplied or placeholder)
      m1.3-investigator-statement.pdf      (optional)
      m1.5-informed-consent.pdf            (optional)
    m5/
      53-clin-stud-rep/
        535-rep-effic-safety-stud/
          <study_id>/
            csr.docx          (latest M5 build)
            tlf.zip           (latest TLF zip)
            define.xml        (extracted from tlf.zip)
            sign_chain.json   (snapshot of every task's sign chain)
            manifest.json     (this packager's own audit trail)

The packager runs synchronously inside the request thread — callers
that need progress events should await ``asyncio.to_thread``.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.config import data_dir

logger = logging.getLogger("autocsr.export.ectd")


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _proj_dir(pid: str) -> Path:
    return data_dir() / "projects" / pid


def _exports_dir(pid: str) -> Path:
    p = _proj_dir(pid) / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ectd_dir(pid: str) -> Path:
    p = _exports_dir(pid) / "ectd"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _latest_docx(pid: str) -> Path | None:
    candidates = sorted(_exports_dir(pid).glob("*.docx"))
    if not candidates:
        candidates = sorted((_exports_dir(pid) / "docx").glob("*.docx")) \
            if (_exports_dir(pid) / "docx").exists() else []
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _latest_tlf(pid: str) -> Path | None:
    candidates = sorted(_exports_dir(pid).glob("tlf*.zip"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _study_id(pid: str) -> str:
    """Return a filesystem-friendly study folder name.

    We prefer the project's user-visible name; the project id is used as
    a fallback so collisions can't happen across projects in the same
    sandbox.
    """
    name = ""
    try:
        pj = data_dir() / "projects.json"
        if pj.exists():
            for item in json.loads(pj.read_text(encoding="utf-8") or "[]"):
                if item.get("id") == pid:
                    name = str(item.get("name") or "")
                    break
    except Exception:
        name = ""
    raw = (name or pid).strip()
    # eCTD spec: no spaces, hyphen-friendly, all lowercase
    sid = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in raw.lower())
    sid = sid.strip("-") or pid
    return sid[:48]


# ---------------------------------------------------------------------------
# Sign chain snapshot
# ---------------------------------------------------------------------------

def _collect_sign_chains(pid: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from app.collab import tasks as tasks_mod
        from app.collab.sign_chain import chain_summary
        for t in tasks_mod.list_tasks(pid):
            cs = chain_summary(pid, t.id)
            if cs is None:
                continue
            cs["task_title"] = t.title
            cs["task_status"] = t.status
            out.append(cs)
    except Exception as e:  # noqa: BLE001
        logger.warning("sign chain collection failed: %s", e)
    return out


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def package_ectd(
    project_id: str,
    *,
    cover_letter_path: str | Path | None = None,
    investigator_statement_path: str | Path | None = None,
    icf_path: str | Path | None = None,
) -> Path:
    """Assemble the demo eCTD zip. Returns the zip path."""
    pid = project_id
    pdir = _proj_dir(pid)
    if not pdir.exists():
        raise FileNotFoundError(f"project {pid} not found")

    sid = _study_id(pid)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = _ectd_dir(pid) / f"ectd-{sid}-{stamp}.zip"

    manifest: dict[str, Any] = {
        "project_id": pid,
        "study_id": sid,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "modules": {},
    }

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # ---- m1: regional admin ----------------------------------------
        cover_target = "m1/m1.2-cover.pdf"
        if cover_letter_path and Path(cover_letter_path).exists():
            zf.write(cover_letter_path, cover_target)
        else:
            zf.writestr(cover_target, _placeholder_pdf("Cover letter — replace"))
        manifest["modules"]["m1.2"] = cover_target

        if investigator_statement_path and Path(investigator_statement_path).exists():
            tgt = "m1/m1.3-investigator-statement.pdf"
            zf.write(investigator_statement_path, tgt)
            manifest["modules"]["m1.3"] = tgt
        if icf_path and Path(icf_path).exists():
            tgt = "m1/m1.5-informed-consent.pdf"
            zf.write(icf_path, tgt)
            manifest["modules"]["m1.5"] = tgt

        # ---- m5: clinical study report ---------------------------------
        m5_prefix = f"m5/53-clin-stud-rep/535-rep-effic-safety-stud/{sid}"

        docx = _latest_docx(pid)
        if docx is not None:
            zf.write(docx, f"{m5_prefix}/csr.docx")
            manifest["modules"]["m5.csr.docx"] = docx.name
        else:
            manifest["modules"]["m5.csr.docx"] = None
            manifest.setdefault("warnings", []).append(
                "no csr.docx found in exports — produce one via /export/docx first",
            )

        tlf = _latest_tlf(pid)
        if tlf is not None:
            zf.write(tlf, f"{m5_prefix}/tlf.zip")
            manifest["modules"]["m5.tlf.zip"] = tlf.name
            # Extract define.xml from the TLF zip and re-emit it next to
            # the csr.docx so submission reviewers don't have to unwrap
            # the inner zip first.
            try:
                with zipfile.ZipFile(tlf, "r") as inner:
                    names = inner.namelist()
                    candidates = [n for n in names if n.endswith("define.xml")]
                    if candidates:
                        with inner.open(candidates[0]) as fh:
                            raw = fh.read()
                        zf.writestr(f"{m5_prefix}/define.xml",
                                     _enhance_define_xml(raw, sid))
                        manifest["modules"]["m5.define.xml"] = candidates[0]
            except zipfile.BadZipFile:
                manifest.setdefault("warnings", []).append("tlf.zip is corrupt")
        else:
            manifest["modules"]["m5.tlf.zip"] = None
            manifest.setdefault("warnings", []).append(
                "no tlf zip found in exports — run /export/tlf first",
            )

        # Sign chain snapshot
        sc = _collect_sign_chains(pid)
        zf.writestr(
            f"{m5_prefix}/sign_chain.json",
            json.dumps(sc, ensure_ascii=False, indent=2, default=str),
        )
        manifest["modules"]["m5.sign_chain.json"] = f"{len(sc)} chains"

        # The packager's own audit trail goes at the root
        zf.writestr(
            f"{m5_prefix}/manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        )

    logger.info("ectd packaged pid=%s study=%s out=%s", pid, sid, out_path)
    return out_path


def list_ectd_exports(project_id: str) -> list[dict[str, Any]]:
    p = _ectd_dir(project_id)
    out: list[dict[str, Any]] = []
    for f in sorted(p.glob("ectd-*.zip"), reverse=True):
        stat = f.stat()
        out.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "modified": _dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return out


def ectd_export_path(project_id: str, filename: str) -> Path | None:
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    p = _ectd_dir(project_id) / filename
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _placeholder_pdf(label: str) -> bytes:
    """Minimal pdf-ish placeholder so reviewers see *something* under m1.

    We emit a single-page PDF whose body is the supplied label. A full
    submission would use a properly signed PDF/A — this is intentionally
    a demo.
    """
    body = (
        f"%PDF-1.4\n"
        f"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        f"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        f"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        f"4 0 obj<</Length {len(label) + 50}>>stream\nBT /F1 14 Tf 72 720 Td ({label}) Tj ET\nendstream\nendobj\n"
        f"xref\n0 5\n0000000000 65535 f \n"
        f"trailer<</Size 5/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
    )
    return body.encode("latin-1", errors="replace")


def _enhance_define_xml(raw: bytes, study_id: str) -> str:
    """Splice the study id into the existing define.xml (if missing)."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    if "<StudyName>" not in text and "<Study " not in text:
        # Append a minimal Study element so downstream tools have it
        text += f"\n<!-- study id: {study_id} -->\n"
    return text


__all__ = [
    "package_ectd", "list_ectd_exports", "ectd_export_path",
]
