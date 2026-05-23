"""Reference formatter (M20 v2.2).

Supports three citation styles for the DOCX/PDF/HTML References chapter:

  - vancouver   (default — NLM / NEJM / Lancet / JAMA)
  - gb7714      (中国国标 GB/T 7714-2015)
  - ama         (American Medical Association)

Input: a list of "literature block"-like dicts. Either:
  - a corpus Block.meta dict with keys
    {title, authors, year, journal, volume?, issue?, pages?, doi?, url?}
  - a Paper dict from app.agents.literature_search

Output: list of formatted strings (one per reference) ready to drop into
the References chapter.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

logger = logging.getLogger("autocsr.export.reference_formatter")

ReferenceStyle = Literal["vancouver", "gb7714", "ama"]


def _safe(d: dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _authors(block: dict[str, Any]) -> list[str]:
    authors = block.get("authors")
    if isinstance(authors, list):
        return [str(a).strip() for a in authors if str(a).strip()]
    raw = str(authors or "").strip()
    if not raw:
        return []
    # Comma- or semicolon-separated fallback
    if ";" in raw:
        return [a.strip() for a in raw.split(";") if a.strip()]
    return [a.strip() for a in raw.split(",") if a.strip()]


def _format_authors_vancouver(authors: list[str], *, max_n: int = 6) -> str:
    """Vancouver: up to 6 authors then ', et al.' """
    if not authors:
        return ""
    if len(authors) > max_n:
        return ", ".join(authors[:max_n]) + ", et al"
    return ", ".join(authors)


def _format_authors_gb7714(authors: list[str], *, max_n: int = 3) -> str:
    """GB/T 7714-2015: first 3 authors then '等' """
    if not authors:
        return ""
    if len(authors) > max_n:
        return ", ".join(authors[:max_n]) + ", 等"
    return ", ".join(authors)


def _format_authors_ama(authors: list[str], *, max_n: int = 6) -> str:
    """AMA: up to 6 authors then ', et al.' (same as Vancouver-style for
    author list — diverges on full DOI rendering)."""
    if not authors:
        return ""
    if len(authors) > max_n:
        return ", ".join(authors[:max_n]) + ", et al"
    return ", ".join(authors)


def _vol_issue_pages(block: dict[str, Any]) -> str:
    """Render ``;15(3):123-130`` if available, else as much as we have."""
    vol = _safe(block, "volume", "vol")
    issue = _safe(block, "issue", "iss", "number")
    pages = _safe(block, "pages", "page")
    if vol and issue and pages:
        return f";{vol}({issue}):{pages}"
    if vol and pages:
        return f";{vol}:{pages}"
    if vol and issue:
        return f";{vol}({issue})"
    if vol:
        return f";{vol}"
    if pages:
        return f":{pages}"
    return ""


def format_vancouver(block: dict[str, Any], *, n: int) -> str:
    authors = _format_authors_vancouver(_authors(block))
    title = _safe(block, "title").rstrip(".")
    journal = _safe(block, "journal", "publication", "publisher")
    year = _safe(block, "year", "publication_year")
    vip = _vol_issue_pages(block)
    parts = [f"{n}."]
    if authors:
        parts.append(f"{authors}.")
    if title:
        parts.append(f"{title}.")
    if journal:
        parts.append(f"{journal}.")
    if year:
        parts.append(f"{year}{vip}.")
    elif vip:
        parts.append(vip.lstrip(";").rstrip(".") + ".")
    return " ".join(parts).strip()


def format_gb7714(block: dict[str, Any], *, n: int) -> str:
    authors = _format_authors_gb7714(_authors(block))
    title = _safe(block, "title").rstrip(".")
    journal = _safe(block, "journal", "publication", "publisher")
    year = _safe(block, "year", "publication_year")
    vol = _safe(block, "volume", "vol")
    issue = _safe(block, "issue", "iss", "number")
    pages = _safe(block, "pages", "page")
    doc_type = block.get("doc_type") or "J"   # default Journal
    head = f"[{n}]"
    parts = [head]
    if authors:
        parts.append(f"{authors}.")
    if title:
        parts.append(f"{title}[{doc_type}].")
    tail_bits: list[str] = []
    if journal:
        tail_bits.append(journal)
    if year:
        tail_bits.append(f", {year}")
    if vol and issue and pages:
        tail_bits.append(f", {vol}({issue}): {pages}")
    elif vol and pages:
        tail_bits.append(f", {vol}: {pages}")
    elif vol:
        tail_bits.append(f", {vol}")
    elif pages:
        tail_bits.append(f": {pages}")
    if tail_bits:
        parts.append("".join(tail_bits).strip(", ") + ".")
    return " ".join(parts).strip()


def format_ama(block: dict[str, Any], *, n: int) -> str:
    authors = _format_authors_ama(_authors(block))
    title = _safe(block, "title").rstrip(".")
    journal = _safe(block, "journal", "publication", "publisher")
    year = _safe(block, "year", "publication_year")
    vip = _vol_issue_pages(block)
    doi = _safe(block, "doi")
    parts = [f"{n}."]
    if authors:
        parts.append(f"{authors}.")
    if title:
        parts.append(f"{title}.")
    if journal:
        parts.append(f"{journal}.")
    if year:
        parts.append(f"{year}{vip}.")
    elif vip:
        parts.append(vip.lstrip(";").rstrip(".") + ".")
    if doi:
        parts.append(f"doi:{doi}")
    return " ".join(parts).strip()


def format_references(blocks: list[dict[str, Any]], *,
                        style: ReferenceStyle = "vancouver",
                        start_n: int = 1) -> list[str]:
    """Format a list of literature-block dicts. Skips empty entries."""
    style = (style or "vancouver").lower()  # type: ignore[assignment]
    fmt = {
        "vancouver": format_vancouver,
        "gb7714": format_gb7714,
        "ama": format_ama,
    }.get(style, format_vancouver)
    out: list[str] = []
    for i, blk in enumerate(blocks):
        if not isinstance(blk, dict):
            continue
        out.append(fmt(blk, n=start_n + i))
    return out


__all__ = [
    "ReferenceStyle",
    "format_vancouver",
    "format_gb7714",
    "format_ama",
    "format_references",
]
