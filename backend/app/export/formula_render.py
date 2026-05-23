"""LaTeX -> PNG formula rendering (M20 v2.2).

Uses matplotlib's built-in mathtext renderer — a sizeable LaTeX subset
(symbols, fractions, sums, integrals, Greek, sub/superscripts, accents).
We deliberately avoid mathjax / LuaTeX so the deployment footprint stays
small.

Public API:

    render_latex_to_png(latex, *, dpi=300, fontsize=12) -> bytes
    extract_math_spans(markdown) -> list[(kind, latex, span_start, span_end)]
                                    kind: 'block' (``$$...$$``) | 'inline' (``$...$``)
"""
from __future__ import annotations

import io
import logging
import re
from typing import Literal

logger = logging.getLogger("autocsr.export.formula_render")

MathKind = Literal["block", "inline"]

# Match block math first ($$...$$), then inline ($...$). Block math may span
# multiple lines; inline math must not contain a newline.
_BLOCK_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_RE = re.compile(r"(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)")


def render_latex_to_png(latex: str, *, dpi: int = 300,
                          fontsize: int = 12, color: str = "black") -> bytes:
    """Render a LaTeX expression to PNG bytes via matplotlib mathtext.

    Caller must ensure ``latex`` is a single expression (no ``$`` delimiters
    inside). On render failure returns a fallback rendering of the raw text.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import mathtext as _mathtext

    expr = (latex or "").strip()
    if not expr:
        return b""
    # mathtext expects $...$ wrapper
    wrapped = f"${expr}$"
    fig = plt.figure(figsize=(0.01, 0.01))
    try:
        text = fig.text(0, 0, wrapped, fontsize=fontsize, color=color)
        # Render once at the target dpi to get the actual bbox
        renderer = fig.canvas.get_renderer()
        bbox = text.get_window_extent(renderer=renderer)
        # Convert bbox in display units to inches at given dpi
        width_in = max(bbox.width / dpi, 0.15)
        height_in = max(bbox.height / dpi, 0.15)
        fig.set_size_inches(width_in + 0.05, height_in + 0.05)
        buf = io.BytesIO()
        fig.savefig(buf, dpi=dpi, format="png",
                    bbox_inches="tight", pad_inches=0.02,
                    transparent=True)
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:        # noqa: BLE001
        # Fall back to plain text rendering — never crash the export
        plt.close(fig)
        logger.warning("latex_render_failed expr=%r err=%s", expr[:80], e)
        fig2 = plt.figure(figsize=(2.4, 0.5))
        fig2.text(0.02, 0.5, expr, fontsize=fontsize, va="center",
                   family="monospace", color=color)
        buf = io.BytesIO()
        fig2.savefig(buf, dpi=dpi, format="png",
                      bbox_inches="tight", pad_inches=0.02, transparent=True)
        import matplotlib.pyplot as plt2
        plt2.close(fig2)
        return buf.getvalue()


def extract_math_spans(markdown: str) -> list[tuple[MathKind, str, int, int]]:
    """Return ``(kind, latex, start, end)`` tuples in source order.

    ``end`` is exclusive. Block matches are emitted before inline matches in
    overlapping order — we walk the string linearly so each character is
    classified at most once.
    """
    if not markdown:
        return []
    out: list[tuple[MathKind, str, int, int]] = []
    consumed_until = 0
    # Build a sorted list of all candidate matches; resolve overlaps by
    # preferring block math (longer / explicit).
    candidates: list[tuple[int, int, MathKind, str]] = []
    for m in _BLOCK_RE.finditer(markdown):
        candidates.append((m.start(), m.end(), "block", m.group(1).strip()))
    for m in _INLINE_RE.finditer(markdown):
        candidates.append((m.start(), m.end(), "inline", m.group(1).strip()))
    # Sort by start, then prefer longer (block) over shorter at same start
    candidates.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    for start, end, kind, latex in candidates:
        if start < consumed_until:
            continue
        out.append((kind, latex, start, end))
        consumed_until = end
    return out


__all__ = ["render_latex_to_png", "extract_math_spans"]
