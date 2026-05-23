"""Locale-aware formatting helpers (M17).

We use :mod:`babel` when available (richer locale data, gettext-friendly)
and fall back to stdlib otherwise so the open-source build stays
zero-dependency for this surface. Both paths produce stable output that
the docx_builder + analysis modules can render without per-call
branching.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("autocsr.i18n.format")


# ---------------------------------------------------------------------------
# Babel detection (lazy import inside helpers so import failures stay quiet)
# ---------------------------------------------------------------------------

def _try_babel():
    try:
        from babel import numbers as _bn  # type: ignore[import-not-found]
        from babel.dates import format_datetime as _bdt  # type: ignore[import-not-found]
        return _bn, _bdt
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Locale canonicalisation
# ---------------------------------------------------------------------------

_LOCALE_ALIASES = {
    "zh": "zh_CN",
    "zh-cn": "zh_CN",
    "zh_cn": "zh_CN",
    "zh-tw": "zh_TW",
    "en": "en_US",
    "en-us": "en_US",
}


def _canon(locale: str | None) -> str:
    if not locale:
        return "zh_CN"
    key = str(locale).strip().lower().replace("-", "_")
    return _LOCALE_ALIASES.get(key, locale)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_number(value: float, locale: str = "zh", *, precision: int = 2) -> str:
    loc = _canon(locale)
    bn, _ = _try_babel()
    if bn is not None:
        try:
            return bn.format_decimal(round(value, precision), locale=loc)
        except Exception:
            pass
    # stdlib fallback — group thousands explicitly
    if abs(value) >= 1e6 or abs(value) < 1:
        return f"{value:,.{precision}f}"
    return f"{value:,.{precision}f}"


def format_percent(value: float, locale: str = "zh", *, precision: int = 1) -> str:
    loc = _canon(locale)
    bn, _ = _try_babel()
    if bn is not None:
        try:
            return bn.format_percent(value, locale=loc, format=f"#0.{'0' * precision}%")
        except Exception:
            pass
    return f"{value * 100:.{precision}f}%"


def format_date(
    ts: datetime,
    locale: str = "zh",
    tz: str = "Asia/Shanghai",
    *,
    fmt: str = "medium",
) -> str:
    loc = _canon(locale)
    _, bdt = _try_babel()
    if bdt is not None:
        try:
            return bdt(ts, format=fmt, locale=loc, tzinfo=_resolve_tz(tz))
        except Exception:
            pass
    # stdlib fallback — render in the requested zone if tz lib is present.
    target = ts.astimezone(_resolve_tz(tz) or timezone.utc)
    if loc.startswith("zh"):
        return target.strftime("%Y年%m月%d日 %H:%M")
    return target.strftime("%Y-%m-%d %H:%M")


def format_unit(
    value: float,
    unit: str,
    locale: str = "zh",
    *,
    precision: int = 2,
) -> str:
    """Compact "<value> <unit>" with the few unit conversions clinical
    chemistry actually uses. Extend conservatively — wrong conversions
    are far worse than untranslated units.
    """
    converted_value, converted_unit = _convert_unit(value, unit)
    formatted = format_number(converted_value, locale=locale, precision=precision)
    return f"{formatted} {converted_unit}"


_UNIT_CONVERSIONS: dict[str, tuple[float, str]] = {
    # source unit -> (factor, canonical unit)
    "mg/dl": (0.0555, "mmol/L"),    # glucose; for cholesterol use 0.02586
    "mg/dL": (0.0555, "mmol/L"),
    "g/dl": (10.0, "g/L"),
    "g/dL": (10.0, "g/L"),
    "ng/ml": (1.0, "ng/mL"),
    "mmHg": (1.0, "mmHg"),
}


def _convert_unit(value: float, unit: str) -> tuple[float, str]:
    if unit in _UNIT_CONVERSIONS:
        factor, target = _UNIT_CONVERSIONS[unit]
        return value * factor, target
    return value, unit


def _resolve_tz(tz: str | None):
    if not tz:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz)
    except Exception:
        return None


def format_p_value(p: float, locale: str = "zh") -> str:
    """Compact P-value renderer respecting the cliched <0.001 cut."""
    if p < 0.001:
        return "P < 0.001" if not _canon(locale).startswith("zh") else "P＜0.001"
    return f"P = {format_number(p, locale, precision=3)}"


__all__ = [
    "format_number", "format_percent", "format_date", "format_unit",
    "format_p_value",
]
