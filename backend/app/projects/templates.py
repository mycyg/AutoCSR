"""Project templates (M12).

Each template lives under ``data/templates/<template_id>/`` and carries:

* ``template.json``  — metadata (id, name, description, principle_id,
  language, tags, notes, …)
* ``README.md``      — human-readable description (optional)
* additional preset files (future: example outline overrides, sample CSV)

The loader scans the directory once per call (cheap, ~4 entries) so authors
can drop new templates without restarting the server. We never trust the
``id`` field in JSON — the directory name is canonical.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProjectTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    principle_id: str | None = None
    language: str = "zh"
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    readme: str | None = None


def template_root() -> Path:
    """Resolve repo-root ``data/templates`` regardless of CWD."""
    # backend/app/projects/templates.py -> backend/app/projects -> backend/app
    # -> backend -> repo root
    return Path(__file__).resolve().parents[3] / "data" / "templates"


def list_templates() -> list[ProjectTemplate]:
    root = template_root()
    out: list[ProjectTemplate] = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        meta = child / "template.json"
        if not meta.exists():
            continue
        try:
            raw: dict[str, Any] = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        raw["id"] = child.name  # directory name is canonical
        readme_p = child / "README.md"
        if readme_p.exists():
            try:
                raw["readme"] = readme_p.read_text(encoding="utf-8")
            except Exception:
                raw["readme"] = None
        try:
            out.append(ProjectTemplate(**raw))
        except Exception:
            # Skip malformed template silently — never block the listing.
            continue
    return out


def get_template(template_id: str) -> ProjectTemplate | None:
    for t in list_templates():
        if t.id == template_id:
            return t
    return None
