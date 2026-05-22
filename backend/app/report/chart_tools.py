"""Chart tooling — bridge matplotlib / plotly / ECharts.

Three responsibilities:

  * ``matplotlib_to_png`` — save a matplotlib Figure to a PNG file we can
    embed into the exported DOCX.
  * ``plotly_to_json_and_png`` — capture both ECharts-style JSON (for the
    interactive frontend) and a PNG (for DOCX). Uses ``plotly.io.to_json``
    plus ``kaleido`` when available; falls back to JSON-only if kaleido is
    not installed (M8 dependencies make kaleido optional).
  * ``echarts_from_dataframe`` — turn a pandas DataFrame into an ECharts
    option dict so the analyst LLM can emit a config without owning the
    chart library directly.

All entry points are pure (no network, no project FS coupling). The sandbox
can call them — they appear in the AST guard's allowed module list.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Literal


ChartType = Literal["bar", "line", "scatter", "boxplot", "pie"]


# ---------------------------------------------------------------------------
# matplotlib → PNG
# ---------------------------------------------------------------------------

def matplotlib_to_png(fig: Any, out_path: str | Path, *, dpi: int = 144) -> Path:
    """Save a matplotlib Figure to PNG.

    ``fig`` is a ``matplotlib.figure.Figure``. We don't import matplotlib at
    module load so this file stays cheap when only ECharts JSON is needed.
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(p), dpi=dpi, bbox_inches="tight")
    return p


# ---------------------------------------------------------------------------
# plotly → JSON + PNG
# ---------------------------------------------------------------------------

def plotly_to_json_and_png(
    fig: Any,
    out_dir: str | Path,
    *,
    basename: str = "plot",
) -> tuple[dict[str, Any], Path | None]:
    """Capture plotly ``fig`` as JSON and (best-effort) PNG.

    Returns ``(chart_json, png_path)`` where ``png_path`` may be ``None`` if
    kaleido is not installed. We never raise on the PNG side because the
    interactive ECharts view is the primary surface.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import plotly.io as pio  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"plotly not available: {e}")
    raw = pio.to_json(fig, validate=False, pretty=False)
    chart_json = json.loads(raw)
    png_path: Path | None = None
    try:
        png_path = out_dir / f"{basename}.png"
        pio.write_image(fig, str(png_path), format="png", scale=2)
    except Exception:
        png_path = None
    return chart_json, png_path


# ---------------------------------------------------------------------------
# DataFrame → ECharts option
# ---------------------------------------------------------------------------

def echarts_from_dataframe(
    df: Any,
    *,
    chart_type: ChartType = "bar",
    x_col: str | None = None,
    y_cols: list[str] | None = None,
    title: str = "",
    stack: bool = False,
    smooth: bool = False,
) -> dict[str, Any]:
    """Turn a DataFrame into an ECharts option dict.

    * For bar / line: ``x_col`` becomes the xAxis categorical labels; each
      ``y_cols`` entry becomes one series.
    * For scatter: each ``y_cols`` entry becomes one scatter series of
      ``[x, y]`` pairs.
    * For pie: first ``y_cols`` column counted by ``x_col`` values, single
      series of ``{name, value}`` items.
    * For boxplot: every ``y_cols`` column gets a boxplot series; if
      ``x_col`` is given we group rows by it (one box per group per col).

    Always returns a dict containing ``title``, ``tooltip``, ``legend``,
    plus ``series`` and (for bar/line/scatter/boxplot) ``xAxis`` /
    ``yAxis`` keys — the e2e test asserts those keys exist.
    """
    import pandas as pd  # type: ignore — lazy import keeps module import cheap

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    cols = list(df.columns)
    if not cols:
        return {"title": {"text": title}, "series": [], "xAxis": {}, "yAxis": {}}

    y_cols = list(y_cols) if y_cols else [c for c in cols if c != x_col]
    if not y_cols:
        y_cols = cols[:1]

    base: dict[str, Any] = {
        "title": {"text": title or ""},
        "tooltip": {"trigger": "axis" if chart_type != "pie" else "item"},
        "legend": {"data": list(y_cols)},
    }

    if chart_type in ("bar", "line"):
        x_data = (
            [str(v) for v in df[x_col].tolist()]
            if (x_col and x_col in df.columns)
            else [str(i) for i in range(len(df))]
        )
        series: list[dict[str, Any]] = []
        for col in y_cols:
            if col not in df.columns:
                continue
            s = pd.to_numeric(df[col], errors="coerce")
            values = [None if pd.isna(v) else float(v) for v in s.tolist()]
            entry: dict[str, Any] = {
                "name": col,
                "type": chart_type,
                "data": values,
            }
            if stack:
                entry["stack"] = "total"
            if smooth and chart_type == "line":
                entry["smooth"] = True
            series.append(entry)
        base.update({
            "xAxis": {"type": "category", "data": x_data},
            "yAxis": {"type": "value"},
            "series": series,
        })
        return base

    if chart_type == "scatter":
        series = []
        x_series = (
            pd.to_numeric(df[x_col], errors="coerce")
            if (x_col and x_col in df.columns)
            else pd.Series(range(len(df)))
        )
        for col in y_cols:
            if col not in df.columns:
                continue
            y_series = pd.to_numeric(df[col], errors="coerce")
            pts = []
            for xv, yv in zip(x_series.tolist(), y_series.tolist()):
                if pd.isna(xv) or pd.isna(yv):
                    continue
                pts.append([float(xv), float(yv)])
            series.append({"name": col, "type": "scatter", "data": pts})
        base.update({
            "xAxis": {"type": "value", "name": x_col or ""},
            "yAxis": {"type": "value"},
            "series": series,
            "tooltip": {"trigger": "item"},
        })
        return base

    if chart_type == "pie":
        # Aggregate: count rows of x_col, weighted by first y_col if numeric.
        if x_col and x_col in df.columns:
            grp = df[x_col].astype(str).fillna("(missing)")
            if y_cols and y_cols[0] in df.columns:
                vals = pd.to_numeric(df[y_cols[0]], errors="coerce").fillna(0)
                agg = vals.groupby(grp).sum()
            else:
                agg = grp.value_counts()
        else:
            agg = pd.Series([len(df)], index=["count"])
        data = [{"name": str(k), "value": float(v)} for k, v in agg.items()]
        base.update({
            "series": [{"name": title or "pie", "type": "pie", "data": data}],
        })
        # pie still uses these axis fields as empty dicts so consumers can
        # uniformly read .xAxis / .yAxis.
        base["xAxis"] = {}
        base["yAxis"] = {}
        return base

    if chart_type == "boxplot":
        # echarts boxplot uses [min, Q1, median, Q3, max] per category.
        if x_col and x_col in df.columns:
            cats = sorted(df[x_col].dropna().astype(str).unique().tolist())
        else:
            cats = ["All"]
        series = []
        for col in y_cols:
            if col not in df.columns:
                continue
            stats_data: list[list[float]] = []
            for cat in cats:
                if x_col and x_col in df.columns:
                    sub = pd.to_numeric(df[df[x_col].astype(str) == cat][col], errors="coerce").dropna()
                else:
                    sub = pd.to_numeric(df[col], errors="coerce").dropna()
                if sub.empty:
                    stats_data.append([0.0, 0.0, 0.0, 0.0, 0.0])
                    continue
                stats_data.append([
                    float(sub.min()),
                    float(sub.quantile(0.25)),
                    float(sub.median()),
                    float(sub.quantile(0.75)),
                    float(sub.max()),
                ])
            series.append({"name": col, "type": "boxplot", "data": stats_data})
        base.update({
            "xAxis": {"type": "category", "data": cats},
            "yAxis": {"type": "value"},
            "series": series,
        })
        return base

    # Unknown chart_type — return empty skeleton.
    return {
        "title": {"text": title or ""},
        "tooltip": {},
        "legend": {"data": list(y_cols)},
        "xAxis": {},
        "yAxis": {},
        "series": [],
    }


# ---------------------------------------------------------------------------
# Markdown table parsing helper (used by analyst stdout parser)
# ---------------------------------------------------------------------------

def find_markdown_tables(text: str) -> list[str]:
    """Return every contiguous markdown-table block found in ``text``.

    Each result is a single string with header + alignment row + data rows
    (one table per result, in document order). Very tolerant — accepts
    GitHub-flavour pipes with or without leading/trailing ``|``.
    """
    if not text:
        return []
    lines = text.splitlines()
    out: list[str] = []
    cur: list[str] = []
    for ln in lines:
        if "|" in ln and ln.strip().startswith("|") is False and ln.strip().endswith("|") is False:
            # Still allow lines like "a | b" without leading pipe
            stripped = ln.strip()
        else:
            stripped = ln.strip()
        if "|" in stripped:
            cur.append(ln)
        else:
            if len(cur) >= 2 and any("---" in c or ":-:" in c for c in cur):
                out.append("\n".join(cur))
            cur = []
    if len(cur) >= 2 and any("---" in c or ":-:" in c for c in cur):
        out.append("\n".join(cur))
    return out
