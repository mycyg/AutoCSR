"""Advanced DOCX template configuration (M13).

Holds the :class:`DocxTemplateConfig` Pydantic model + a small library of
named presets. The builder consumes the config to nudge styles
(fonts/sizes/colors), page margins, line-spacing, header/footer text, and
an optional watermark / AI-provenance shading.

Configurations persist per-project at
``data/projects/<pid>/exports/template_config.json``. Missing values
fall back to the standard preset.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import data_dir


PresetId = Literal["standard", "pharma", "academic", "regulatory"]


class FontConfig(BaseModel):
    heading: str = "SimHei"
    body: str = "SimSun"
    code: str = "Consolas"


class SizeConfig(BaseModel):
    h1: int = 18
    h2: int = 16
    h3: int = 14
    body: int = 11


class ColorConfig(BaseModel):
    heading: str = "#000000"
    body: str = "#000000"
    link: str = "#0000FF"


class MarginConfig(BaseModel):
    top: float = 2.54     # cm
    bottom: float = 2.54
    left: float = 3.17
    right: float = 3.17


class DocxTemplateConfig(BaseModel):
    preset: PresetId = "standard"
    fonts: FontConfig = Field(default_factory=FontConfig)
    sizes: SizeConfig = Field(default_factory=SizeConfig)
    colors: ColorConfig = Field(default_factory=ColorConfig)
    margins: MarginConfig = Field(default_factory=MarginConfig)
    line_spacing: float = 1.5
    toc_depth: int = 3
    header_text: str = ""
    footer_text: str = ""
    watermark: str = ""
    show_ai_provenance: bool = False
    custom_template_id: str | None = None  # M13 upload reference


def _preset(name: PresetId) -> DocxTemplateConfig:
    """Return a fresh instance preconfigured for ``name``."""
    if name == "standard":
        return DocxTemplateConfig(preset="standard")
    if name == "pharma":
        return DocxTemplateConfig(
            preset="pharma",
            fonts=FontConfig(heading="Arial", body="Times New Roman", code="Consolas"),
            sizes=SizeConfig(h1=20, h2=16, h3=14, body=11),
            colors=ColorConfig(heading="#1F2937", body="#000000", link="#1D4ED8"),
            margins=MarginConfig(top=2.54, bottom=2.54, left=3.17, right=2.54),
            line_spacing=1.5,
            toc_depth=3,
            header_text="Clinical Study Report",
            footer_text="Confidential — for internal review",
        )
    if name == "academic":
        return DocxTemplateConfig(
            preset="academic",
            fonts=FontConfig(heading="Times New Roman", body="Times New Roman", code="Consolas"),
            sizes=SizeConfig(h1=16, h2=14, h3=12, body=12),
            colors=ColorConfig(heading="#000000", body="#000000", link="#0000FF"),
            margins=MarginConfig(top=2.54, bottom=2.54, left=2.54, right=2.54),
            line_spacing=2.0,
            toc_depth=4,
            header_text="",
            footer_text="",
        )
    if name == "regulatory":
        return DocxTemplateConfig(
            preset="regulatory",
            fonts=FontConfig(heading="Arial", body="Arial", code="Consolas"),
            sizes=SizeConfig(h1=18, h2=14, h3=12, body=11),
            colors=ColorConfig(heading="#111827", body="#000000", link="#1D4ED8"),
            margins=MarginConfig(top=2.54, bottom=2.54, left=3.5, right=2.0),
            line_spacing=1.5,
            toc_depth=3,
            header_text="REGULATORY SUBMISSION",
            footer_text="Page {page} of {total}",
            watermark="CONFIDENTIAL",
            show_ai_provenance=True,
        )
    return DocxTemplateConfig()


PRESETS: dict[PresetId, DocxTemplateConfig] = {
    "standard": _preset("standard"),
    "pharma": _preset("pharma"),
    "academic": _preset("academic"),
    "regulatory": _preset("regulatory"),
}


def preset_names() -> list[str]:
    return list(PRESETS.keys())


def get_preset(name: str) -> DocxTemplateConfig:
    if name not in PRESETS:
        return PRESETS["standard"]
    # Return a copy so callers can mutate freely.
    return DocxTemplateConfig(**json.loads(PRESETS[name].model_dump_json()))


# ---------------------------------------------------------------------------
# Per-project persistence
# ---------------------------------------------------------------------------


def _config_path(project_id: str) -> Path:
    p = data_dir() / "projects" / project_id / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p / "template_config.json"


def load_config(project_id: str) -> DocxTemplateConfig:
    p = _config_path(project_id)
    if not p.exists():
        return get_preset("standard")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return DocxTemplateConfig(**raw)
    except Exception:
        return get_preset("standard")


def save_config(project_id: str, config: DocxTemplateConfig) -> DocxTemplateConfig:
    p = _config_path(project_id)
    p.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return config


def apply_patch(project_id: str, patch: dict[str, Any]) -> DocxTemplateConfig:
    base = load_config(project_id)
    base_dict = json.loads(base.model_dump_json())
    merged = _deep_merge(base_dict, patch)
    cfg = DocxTemplateConfig(**merged)
    return save_config(project_id, cfg)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
