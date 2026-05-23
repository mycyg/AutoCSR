"""User-uploaded DOCX templates (M13).

Workflow:

1. ``store_uploaded(pid, name, raw_bytes)`` saves the file to
   ``data/projects/<pid>/templates/<template_id>.docx`` and returns a
   small metadata record (id, filename, placeholders found).
2. ``apply_uploaded_template(pid, template_id, mapping)`` opens the
   template via ``python-docx``, substitutes ``{{KEY}}`` placeholders,
   and returns the rendered document object — the caller is responsible
   for appending body sections and saving it.

Placeholder detection looks for ``{{XXX}}`` patterns inside paragraphs
(body + header + footer) so authors can preview which keys they bound.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from docx import Document

from app.config import data_dir

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


def _templates_dir(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path(project_id: str) -> Path:
    return _templates_dir(project_id) / "index.json"


def _load_index(project_id: str) -> list[dict[str, Any]]:
    p = _index_path(project_id)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_index(project_id: str, items: list[dict[str, Any]]) -> None:
    _index_path(project_id).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def list_templates(project_id: str) -> list[dict[str, Any]]:
    return _load_index(project_id)


def store_uploaded(project_id: str, filename: str, raw_bytes: bytes) -> dict[str, Any]:
    """Persist ``raw_bytes`` as a new template file and index it."""
    tid = uuid.uuid4().hex[:10]
    safe_name = (filename or "template.docx").rsplit("/", 1)[-1]
    if not safe_name.lower().endswith(".docx"):
        safe_name = safe_name + ".docx"
    p = _templates_dir(project_id) / f"{tid}.docx"
    p.write_bytes(raw_bytes)
    placeholders = _scan_placeholders(p)
    rec = {
        "id": tid,
        "filename": safe_name,
        "path": str(p),
        "placeholders": sorted(placeholders),
        "size_bytes": p.stat().st_size,
    }
    items = _load_index(project_id)
    items.append(rec)
    _save_index(project_id, items)
    return rec


def template_path(project_id: str, template_id: str) -> Path | None:
    for rec in _load_index(project_id):
        if rec.get("id") == template_id:
            p = Path(rec.get("path") or "")
            return p if p.exists() else None
    return None


def _scan_placeholders(path: Path) -> set[str]:
    try:
        doc = Document(str(path))
    except Exception:
        return set()
    keys: set[str] = set()
    for p in doc.paragraphs:
        for m in _PLACEHOLDER_RE.finditer(p.text or ""):
            keys.add(m.group(1))
    for sec in doc.sections:
        for hf in (sec.header, sec.footer):
            for p in hf.paragraphs:
                for m in _PLACEHOLDER_RE.finditer(p.text or ""):
                    keys.add(m.group(1))
    return keys


def open_uploaded(project_id: str, template_id: str, mapping: dict[str, str]) -> Document:
    """Open the uploaded template and substitute placeholders.

    Caller appends body sections + saves. Returns the live Document.
    """
    p = template_path(project_id, template_id)
    if p is None:
        raise FileNotFoundError(f"template {template_id} not found in project {project_id}")
    doc = Document(str(p))
    _substitute_in_doc(doc, mapping)
    return doc


def _substitute_in_doc(doc: Document, mapping: dict[str, str]) -> None:
    def _patch_paragraph(p) -> None:
        text = "".join(r.text or "" for r in p.runs)
        if "{{" not in text:
            return
        new_text = _PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(1), m.group(0)), text)
        if new_text == text:
            return
        if p.runs:
            keep = p.runs[0]
            keep.text = new_text
            for extra in p.runs[1:]:
                extra.text = ""
    for p in doc.paragraphs:
        _patch_paragraph(p)
    for sec in doc.sections:
        for hf in (sec.header, sec.footer):
            for p in hf.paragraphs:
                _patch_paragraph(p)
