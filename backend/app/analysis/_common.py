"""Shared utilities for analysis modules.

Keeps StatBlock construction, markdown table rendering, and parquet loading
consistent across descriptive / inferential / survival / safety.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from tabulate import tabulate


def new_stat_id() -> str:
    return uuid.uuid4().hex[:12]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_parquet(path: str | Path) -> pd.DataFrame:
    """Read a processed parquet (or csv fallback)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"parquet not found: {p}")
    if p.suffix.lower() == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str, encoding_errors="replace")


def md_table(
    rows: list[list[Any]],
    headers: list[str],
    *,
    align: str | None = None,
) -> str:
    """Render a markdown table with tabulate's `github` flavour.

    ``rows`` may contain pandas NaN — render as blank cell.
    """
    cleaned: list[list[Any]] = []
    for r in rows:
        cleaned.append(["" if (v is None or _is_nan(v)) else v for v in r])
    return tabulate(cleaned, headers=headers, tablefmt="github")


def _is_nan(v: Any) -> bool:
    try:
        return bool(pd.isna(v))
    except Exception:
        return False


def fmt_num(v: Any, digits: int = 2) -> str:
    """Format a numeric cell, blank if NaN."""
    if v is None or _is_nan(v):
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1e6 or (0 < abs(f) < 1e-3):
        return f"{f:.{digits}e}"
    return f"{f:.{digits}f}"


def fmt_pct(num: float, denom: float, digits: int = 1) -> str:
    if denom <= 0 or _is_nan(num) or _is_nan(denom):
        return ""
    return f"{(num / denom) * 100:.{digits}f}"


def filter_df(df: pd.DataFrame, query: str | None) -> pd.DataFrame:
    if not query:
        return df
    try:
        return df.query(query, engine="python")
    except Exception:
        return df


def has_cols(df: pd.DataFrame, cols: list[str]) -> list[str]:
    """Return the subset of ``cols`` actually present in ``df``."""
    upper_map = {c.upper(): c for c in df.columns}
    out: list[str] = []
    for c in cols:
        if c in df.columns:
            out.append(c)
        elif c.upper() in upper_map:
            out.append(upper_map[c.upper()])
    return out


def _to_jsonable(v: Any) -> Any:
    """Cast numpy / pandas scalars to plain Python for json serialization."""
    if v is None:
        return None
    if _is_nan(v):
        return None
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return str(v)
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def jsonable_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Best-effort cast every leaf to json-safe types."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = jsonable_dict(v)
        elif isinstance(v, list):
            out[k] = [jsonable_dict(x) if isinstance(x, dict) else _to_jsonable(x) for x in v]
        else:
            out[k] = _to_jsonable(v)
    return out
