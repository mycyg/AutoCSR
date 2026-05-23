"""Prompt template loader (M13).

Files live under ``backend/app/i18n/prompts/<lang>/<name>.txt``. The loader
keeps an in-memory cache keyed by ``(lang, name)`` and falls back to the
``zh`` template when a non-default language is missing.

``render_prompt`` is a tiny ``str.format_map``-based renderer — no jinja2
dependency. Templates use ``{key}`` placeholders; unknown keys are kept
verbatim (defensive — never crash if a prompt forgot to escape ``{``).
"""
from __future__ import annotations

import string
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_CACHE: dict[tuple[str, str], str] = {}


def prompts_root() -> Path:
    return Path(__file__).parent / "prompts"


def _path(lang: str, name: str) -> Path:
    return prompts_root() / lang / f"{name}.txt"


def has_prompt(name: str, lang: str = "zh") -> bool:
    return _path(lang, name).exists()


def available_prompts(lang: str = "zh") -> list[str]:
    d = prompts_root() / lang
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.txt"))


def load_prompt(name: str, language: str = "zh") -> str:
    """Return the raw template text for ``name`` in ``language`` (with
    fallback to ``zh``). Raises ``FileNotFoundError`` if no template
    found in either language."""
    lang = (language or "zh").lower()
    with _LOCK:
        key = (lang, name)
        if key in _CACHE:
            return _CACHE[key]
    p = _path(lang, name)
    if not p.exists() and lang != "zh":
        p = _path("zh", name)
    if not p.exists():
        raise FileNotFoundError(f"prompt template {name!r} not found (lang={lang})")
    txt = p.read_text(encoding="utf-8")
    with _LOCK:
        _CACHE[key] = txt
    return txt


class _SafeMap(dict):
    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"


def render_prompt(name: str, language: str = "zh", **values: Any) -> str:
    """Load + render with ``str.format_map``. Missing keys are preserved
    so prompts that mix literal braces and named placeholders don't blow
    up. Use ``{{`` / ``}}`` to embed literal braces."""
    template = load_prompt(name, language)
    formatter = string.Formatter()
    try:
        return formatter.vformat(template, (), _SafeMap(values))
    except Exception:
        # Last-resort fallback: return raw template unsubstituted.
        return template
