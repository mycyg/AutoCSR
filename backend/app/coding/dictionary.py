"""Unified coding dictionary facade.

A single process-wide registry that owns one loader instance per system. The
loaders themselves are lazy (data loaded on first access) so import is cheap.

Usage:
    from app.coding import dictionary
    candidates = dictionary.lookup("ICD10", "diabetes", top_k=5)
    info = dictionary.get_code_info("ICD10", "E11")
    systems = dictionary.list_systems()
"""
from __future__ import annotations

import threading
from typing import Any

from app.coding.loaders import (
    ATCLoader, BaseLoader, ICD10Loader, LOINCLoader,
    MedDRALoader, SNOMEDLoader, WHODrugLoader,
)
from app.coding.schemas import CodingCandidate, CodingResult, SystemInfo


_REG_LOCK = threading.Lock()
_REGISTRY: dict[str, BaseLoader] | None = None


def _settings_path(name: str) -> str | None:
    """Look up a configured path for a commercial dictionary."""
    try:
        from app.config import settings
        cfg = settings().get("coding", {}) or {}
        v = cfg.get(name)
        return str(v) if v else None
    except Exception:
        return None


def _build_registry() -> dict[str, BaseLoader]:
    return {
        "ICD10": ICD10Loader(),
        "ATC": ATCLoader(),
        "LOINC": LOINCLoader(),
        "MEDDRA": MedDRALoader(_settings_path("meddra_path")),
        "WHODRUG": WHODrugLoader(_settings_path("whodrug_path")),
        "SNOMED": SNOMEDLoader(_settings_path("snomed_path")),
    }


def _get_registry() -> dict[str, BaseLoader]:
    global _REGISTRY
    if _REGISTRY is None:
        with _REG_LOCK:
            if _REGISTRY is None:
                _REGISTRY = _build_registry()
    return _REGISTRY


def reload() -> None:
    """Drop the cached registry — used when settings change."""
    global _REGISTRY
    with _REG_LOCK:
        _REGISTRY = None


# ---------------------------------------------------------------------- public


def list_systems() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sys_id, loader in _get_registry().items():
        info = loader.info()
        out.append(info.to_dict())
    return out


def get_system_info(system: str) -> SystemInfo | None:
    loader = _get_registry().get(system.upper())
    if not loader:
        return None
    return loader.info()


def lookup(system: str, term: str, top_k: int = 5,
           language: str = "en") -> list[CodingCandidate]:
    """Fuzzy lookup ``term`` against ``system``. Language is a hint only —
    bundled dictionaries are English-first.
    """
    loader = _get_registry().get(system.upper())
    if not loader or not term or not term.strip():
        return []
    return loader.search(term.strip(), top_k=max(1, int(top_k)))


def lookup_many(system: str, terms: list[str], top_k: int = 3,
                language: str = "en") -> dict[str, list[CodingCandidate]]:
    """Convenience: batch lookup. Returns a map from original term to candidates."""
    out: dict[str, list[CodingCandidate]] = {}
    for t in terms:
        if t is None:
            continue
        key = str(t)
        out[key] = lookup(system, key, top_k=top_k, language=language)
    return out


def get_code_info(system: str, code: str) -> CodingResult | None:
    loader = _get_registry().get(system.upper())
    if not loader or not code or not code.strip():
        return None
    return loader.get(code.strip())


def suggest_system_for_column(col_name: str) -> str | None:
    """Heuristic — pick the best dictionary for a column."""
    n = (col_name or "").lower().strip()
    if not n:
        return None
    if "aeterm" in n or "aedecod" in n or "adverse" in n or "soc" in n or "_pt" in n:
        return "MEDDRA"
    if "cmtrt" in n or "cmdecod" in n or "concomitant" in n or "drug" in n or "medication" in n:
        return "WHODRUG"
    if "diagnos" in n or "icd" in n or "mhterm" in n or "mhdecod" in n:
        return "ICD10"
    if "labtest" in n or "lbtest" in n or "loinc" in n or "lab_" in n:
        return "LOINC"
    if "atc" in n:
        return "ATC"
    if "sct" in n or "snomed" in n:
        return "SNOMED"
    return None
