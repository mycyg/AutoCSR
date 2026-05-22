"""Principle loader — exposes hardcoded chapter trees for CSR generation.

A *Principle* is a YAML-defined hierarchy of report sections. AutoCSR ships
three:

  * ich_e3   — ICH E3 Clinical Study Report (full Section 1-16)
  * cde_chem — NMPA / CDE chemistry CSR guideline (simplified)
  * cde_tcm  — NMPA / CDE traditional Chinese medicine guideline (stub)

The loader is read-only: principle YAML is committed source code, not user data.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

_DIR = Path(__file__).parent


class PrincipleSection(BaseModel):
    id: str
    title: str
    required: bool = False
    requirements: list[str] = Field(default_factory=list)
    stat_hints: list[str] = Field(default_factory=list)
    pdf_refs: list[str] = Field(default_factory=list)
    children: list["PrincipleSection"] = Field(default_factory=list)


PrincipleSection.model_rebuild()


class PrincipleMeta(BaseModel):
    id: str
    name: str
    version: str = ""
    scope: list[str] = Field(default_factory=list)


class Principle(BaseModel):
    meta: PrincipleMeta
    sections: list[PrincipleSection]

    def flatten(self) -> list[PrincipleSection]:
        """Depth-first flatten — used by outline builder & PDF indexer."""
        out: list[PrincipleSection] = []

        def _walk(s: PrincipleSection) -> None:
            out.append(s)
            for c in s.children:
                _walk(c)

        for s in self.sections:
            _walk(s)
        return out


class PrincipleSummary(BaseModel):
    id: str
    name: str
    version: str
    scope: list[str]
    section_count: int


def _yaml_path(principle_id: str) -> Path:
    return _DIR / f"{principle_id}.yaml"


def available_ids() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.yaml"))


@lru_cache(maxsize=8)
def load_principle(principle_id: str) -> Principle:
    p = _yaml_path(principle_id)
    if not p.exists():
        raise FileNotFoundError(f"principle not found: {principle_id}")
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Principle.model_validate(data)


def list_principles() -> list[PrincipleSummary]:
    out: list[PrincipleSummary] = []
    for pid in available_ids():
        try:
            pr = load_principle(pid)
        except Exception:
            continue
        out.append(PrincipleSummary(
            id=pr.meta.id, name=pr.meta.name, version=pr.meta.version,
            scope=pr.meta.scope, section_count=len(pr.flatten()),
        ))
    return out


__all__ = [
    "Principle", "PrincipleMeta", "PrincipleSection", "PrincipleSummary",
    "load_principle", "list_principles", "available_ids",
]
