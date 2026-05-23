"""Chart selector agent (M20 v2.2).

Heuristic-driven (no LLM by default) recommender that maps a ``StatBlock``
to an appropriate ECharts chart template + rationale string.

Mapping rules:

  analysis_type == 'descriptive'      -> bar / boxplot
  analysis_type == 'inferential'      -> forest
  analysis_type == 'survival'         -> km / km_with_risk_table
  analysis_type == 'safety'           -> stacked_bar_by_soc / heatmap
  analysis_type == 'subgroup'         -> forest
  analysis_type == 'sensitivity'      -> side_by_side_bar
  analysis_type == 'multitest'        -> bar with annotation
  analysis_type == 'baseline_balance' -> side_by_side_bar
  analysis_type == 'consort'          -> sankey (flowchart fallback to text)
  analysis_type == 'custom'           -> inspect result_json.chart_json or fall back to bar

The returned ``echarts_template_json`` is a runnable ECharts option object —
the frontend can hand it straight to its echarts component (titles + axis
labels filled with placeholders the caller can rewrite).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("autocsr.agents.chart_selector")


ChartType = str   # km / km_with_risk_table / forest / bar / boxplot / stacked_bar / heatmap / side_by_side_bar / sankey / line


@dataclass
class ChartRecommendation:
    chart_type: ChartType
    echarts_template_json: dict[str, Any]
    rationale: str
    confidence: float = 1.0
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chart_type": self.chart_type,
            "echarts_template_json": self.echarts_template_json,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "alternatives": list(self.alternatives),
        }


# ---------------------------------------------------------------------------
# Template factories — small, valid ECharts option dicts
# ---------------------------------------------------------------------------

def _t_bar(title: str = "Bar Chart") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "10%", "right": "5%", "bottom": "12%"},
        "xAxis": {"type": "category", "data": ["A", "B", "C"]},
        "yAxis": {"type": "value"},
        "series": [{
            "type": "bar",
            "data": [10, 20, 30],
            "itemStyle": {"color": "#5470c6"},
        }],
    }


def _t_stacked_bar_soc(title: str = "AE by System Organ Class") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"top": "bottom"},
        "grid": {"left": "20%", "right": "5%", "bottom": "12%"},
        "yAxis": {"type": "category",
                   "data": ["Gastrointestinal", "Nervous", "Skin",
                              "Blood", "Respiratory"]},
        "xAxis": {"type": "value"},
        "series": [
            {"name": "Drug", "type": "bar", "stack": "total",
              "data": [12, 8, 5, 4, 6]},
            {"name": "Placebo", "type": "bar", "stack": "total",
              "data": [7, 9, 3, 2, 4]},
        ],
    }


def _t_boxplot(title: str = "Distribution") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "category",
                   "data": ["Drug", "Placebo"]},
        "yAxis": {"type": "value"},
        "series": [{
            "type": "boxplot",
            # min, Q1, median, Q3, max per category
            "data": [[5, 12, 18, 25, 38], [7, 14, 20, 28, 42]],
        }],
    }


def _t_km(title: str = "Kaplan-Meier Survival", with_risk_table: bool = False
            ) -> dict[str, Any]:
    series = [
        {"name": "Drug A", "type": "line", "step": "end", "showSymbol": False,
          "data": [[0, 1.0], [60, 0.93], [120, 0.84], [180, 0.75],
                    [240, 0.66], [300, 0.58], [360, 0.51]]},
        {"name": "Placebo", "type": "line", "step": "end", "showSymbol": False,
          "data": [[0, 1.0], [60, 0.88], [120, 0.71], [180, 0.55],
                    [240, 0.42], [300, 0.33], [360, 0.26]]},
    ]
    opt: dict[str, Any] = {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": "bottom"},
        "grid": {"left": "10%", "right": "5%",
                  "bottom": "30%" if with_risk_table else "12%"},
        "xAxis": {"type": "value", "name": "Days from randomization"},
        "yAxis": {"type": "value", "min": 0, "max": 1,
                   "name": "Survival probability"},
        "series": series,
    }
    if with_risk_table:
        opt["dataZoom"] = [{"type": "inside"}]
        opt["__risk_table__"] = {
            "rows": [
                {"label": "Drug A",
                  "counts": [40, 36, 32, 28, 24, 18, 12]},
                {"label": "Placebo",
                  "counts": [40, 33, 25, 18, 12, 7, 4]},
            ],
            "timepoints": [0, 60, 120, 180, 240, 300, 360],
        }
    return opt


def _t_forest(title: str = "Subgroup Forest Plot") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "grid": {"left": "25%", "right": "10%", "bottom": "10%"},
        "yAxis": {"type": "category",
                   "data": ["Overall", "Age <65", "Age >=65", "Male", "Female",
                              "PD-L1 >=50%", "PD-L1 <50%"]},
        "xAxis": {"type": "value", "name": "Hazard Ratio",
                   "min": 0.2, "max": 2.0,
                   "axisLine": {"onZero": False}},
        "series": [{
            "type": "scatter",
            "symbolSize": 14,
            "data": [
                [0.72, 0], [0.68, 1], [0.78, 2], [0.74, 3], [0.71, 4],
                [0.59, 5], [0.85, 6],
            ],
            "markLine": {"silent": True, "lineStyle": {"color": "#999"},
                          "data": [{"xAxis": 1.0}]},
        }],
    }


def _t_heatmap(title: str = "AE Heatmap by SOC × Severity") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"position": "top"},
        "grid": {"left": "20%", "right": "10%", "bottom": "15%"},
        "xAxis": {"type": "category",
                   "data": ["Mild", "Moderate", "Severe"]},
        "yAxis": {"type": "category",
                   "data": ["Gastrointestinal", "Nervous", "Skin",
                              "Blood", "Respiratory"]},
        "visualMap": {"min": 0, "max": 30,
                       "calculable": True, "orient": "horizontal",
                       "left": "center", "bottom": "5%"},
        "series": [{
            "type": "heatmap",
            "data": [
                [0, 0, 18], [1, 0, 7], [2, 0, 2],
                [0, 1, 12], [1, 1, 6], [2, 1, 3],
                [0, 2, 5], [1, 2, 4], [2, 2, 1],
                [0, 3, 4], [1, 3, 3], [2, 3, 1],
                [0, 4, 8], [1, 4, 5], [2, 4, 2],
            ],
            "label": {"show": True},
        }],
    }


def _t_side_by_side(title: str = "Sensitivity vs Primary") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": "bottom"},
        "grid": {"left": "10%", "right": "5%", "bottom": "12%"},
        "xAxis": {"type": "category",
                   "data": ["Primary", "PP", "On-treatment", "MI(20)"]},
        "yAxis": {"type": "value", "name": "Effect (HR)"},
        "series": [
            {"name": "Estimate", "type": "bar",
              "data": [0.72, 0.74, 0.69, 0.71]},
            {"name": "Lower 95% CI", "type": "scatter",
              "data": [0.60, 0.61, 0.58, 0.59]},
            {"name": "Upper 95% CI", "type": "scatter",
              "data": [0.86, 0.89, 0.83, 0.85]},
        ],
    }


def _t_sankey(title: str = "Patient Flow (CONSORT)") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "item"},
        "series": [{
            "type": "sankey",
            "data": [
                {"name": "Screened"}, {"name": "Randomized"},
                {"name": "Drug"}, {"name": "Placebo"},
                {"name": "Completed Drug"}, {"name": "Discontinued Drug"},
                {"name": "Completed Placebo"}, {"name": "Discontinued Placebo"},
            ],
            "links": [
                {"source": "Screened", "target": "Randomized", "value": 240},
                {"source": "Randomized", "target": "Drug", "value": 120},
                {"source": "Randomized", "target": "Placebo", "value": 120},
                {"source": "Drug", "target": "Completed Drug", "value": 102},
                {"source": "Drug", "target": "Discontinued Drug", "value": 18},
                {"source": "Placebo", "target": "Completed Placebo", "value": 95},
                {"source": "Placebo", "target": "Discontinued Placebo", "value": 25},
            ],
        }],
    }


def _t_line(title: str = "Trend Over Time") -> dict[str, Any]:
    return {
        "title": {"text": title, "left": "center"},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": "bottom"},
        "grid": {"left": "10%", "right": "5%", "bottom": "12%"},
        "xAxis": {"type": "category",
                   "data": ["BL", "W4", "W8", "W12", "W24"]},
        "yAxis": {"type": "value"},
        "series": [
            {"name": "Drug", "type": "line",
              "data": [100, 92, 84, 78, 70]},
            {"name": "Placebo", "type": "line",
              "data": [100, 98, 95, 94, 92]},
        ],
    }


# ---------------------------------------------------------------------------
# Recommendation entrypoint
# ---------------------------------------------------------------------------

_DEFAULT_TITLE = "AutoCSR chart"


def _coerce_stat_block(stat_block: Any) -> dict[str, Any]:
    """Accept a StatBlock model, dict, or Pydantic object."""
    if isinstance(stat_block, dict):
        return stat_block
    if hasattr(stat_block, "model_dump"):
        return stat_block.model_dump()
    if hasattr(stat_block, "__dict__"):
        return dict(stat_block.__dict__)
    raise ValueError("stat_block must be a StatBlock-like object")


def recommend_chart(stat_block: Any) -> ChartRecommendation:
    """Map a StatBlock to a chart recommendation."""
    sb = _coerce_stat_block(stat_block)
    atype = str(sb.get("analysis_type") or "").lower()
    title = str(sb.get("title") or _DEFAULT_TITLE)
    params = sb.get("params") or {}
    result = sb.get("result_json") or {}

    # Survival ----------------------------------------------------------
    if atype == "survival":
        with_rt = bool(params.get("risk_table") or params.get("with_risk_table")
                        or "PFS" in title.upper() or "OS" in title.upper())
        chart = "km_with_risk_table" if with_rt else "km"
        opt = _t_km(title=title, with_risk_table=with_rt)
        return ChartRecommendation(
            chart_type=chart,
            echarts_template_json=opt,
            rationale=("Survival analyses (KM-style) benefit from a step "
                        "line plot with arm-level curves; a risk table under "
                        "the plot makes the underlying numbers auditable."),
            alternatives=["km", "forest"],
        )

    # Subgroup / inferential -> forest ---------------------------------
    if atype in ("subgroup", "inferential"):
        return ChartRecommendation(
            chart_type="forest",
            echarts_template_json=_t_forest(title=title),
            rationale=("Subgroup or inferential effect estimates display "
                        "most clearly as a forest plot — one row per "
                        "subgroup, point estimate + 95% CI."),
            alternatives=["bar", "side_by_side_bar"],
        )

    # Safety ------------------------------------------------------------
    if atype == "safety":
        # Heatmap if there are 2 categorical axes; else stacked bar
        has_grid = ("SOC" in title.upper() and "GRADE" in title.upper()) \
                    or bool(result.get("heatmap_matrix"))
        if has_grid:
            return ChartRecommendation(
                chart_type="heatmap",
                echarts_template_json=_t_heatmap(title=title),
                rationale=("Two-axis safety summaries (SOC × severity / "
                            "SOC × visit) read most efficiently as a heatmap."),
                alternatives=["stacked_bar_by_soc"],
            )
        return ChartRecommendation(
            chart_type="stacked_bar_by_soc",
            echarts_template_json=_t_stacked_bar_soc(title=title),
            rationale=("AE summaries by SOC × arm are most legible as "
                        "horizontal stacked bars sorted by total incidence."),
            alternatives=["heatmap", "bar"],
        )

    # Sensitivity ------------------------------------------------------
    if atype == "sensitivity":
        return ChartRecommendation(
            chart_type="side_by_side_bar",
            echarts_template_json=_t_side_by_side(title=title),
            rationale=("Sensitivity analyses compare the primary estimate "
                        "against alternative analysis sets — a side-by-side "
                        "bar exposes any divergence."),
            alternatives=["forest"],
        )

    # CONSORT ----------------------------------------------------------
    if atype == "consort":
        return ChartRecommendation(
            chart_type="sankey",
            echarts_template_json=_t_sankey(title=title),
            rationale=("Patient disposition flows naturally render as a "
                        "Sankey diagram (screened → randomized → completed)."),
            alternatives=["bar"],
        )

    # Baseline balance / multitest -------------------------------------
    if atype in ("baseline_balance", "multitest"):
        return ChartRecommendation(
            chart_type="side_by_side_bar",
            echarts_template_json=_t_side_by_side(title=title),
            rationale=("Multi-arm baseline / multitest summaries are most "
                        "compact as side-by-side bars."),
            alternatives=["bar", "heatmap"],
        )

    # Descriptive ------------------------------------------------------
    if atype == "descriptive":
        # If params or markdown suggest distribution, use boxplot; else bar
        md = (sb.get("markdown_table") or "").lower()
        looks_distribution = any(t in md for t in ("median", "iqr", "q1",
                                                     "q3", "min", "max")) \
                              or any(t in title.lower() for t in ("distribution",
                                                                     "boxplot",
                                                                     "summary"))
        if looks_distribution:
            return ChartRecommendation(
                chart_type="boxplot",
                echarts_template_json=_t_boxplot(title=title),
                rationale=("Descriptive summaries with quartile statistics "
                            "render most informatively as a boxplot by arm."),
                alternatives=["bar"],
            )
        return ChartRecommendation(
            chart_type="bar",
            echarts_template_json=_t_bar(title=title),
            rationale=("Categorical descriptive summaries (n, %) read "
                        "cleanly as a grouped bar by arm."),
            alternatives=["boxplot", "stacked_bar_by_soc"],
        )

    # Custom — inspect any pre-supplied chart_json --------------------
    if atype == "custom":
        if isinstance(result.get("chart_json"), dict):
            return ChartRecommendation(
                chart_type="custom",
                echarts_template_json=result["chart_json"],
                rationale=("Analyst-supplied ECharts JSON is used as-is to "
                            "preserve the agent's intended visualisation."),
                alternatives=["bar"],
                confidence=0.85,
            )

    # Default fallback
    return ChartRecommendation(
        chart_type="bar",
        echarts_template_json=_t_bar(title=title),
        rationale=("No specific match for analysis_type='%s' — defaulting "
                    "to a grouped bar chart." % atype),
        alternatives=["boxplot", "forest"],
        confidence=0.5,
    )


__all__ = ["ChartRecommendation", "recommend_chart"]
