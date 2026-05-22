"""Unit tests for chart_tools — ECharts JSON shape sanity."""
from __future__ import annotations

import pandas as pd

from app.report.chart_tools import (
    echarts_from_dataframe,
    find_markdown_tables,
)


def test_bar_has_xaxis_series_legend() -> None:
    df = pd.DataFrame({
        "group": ["A", "B", "C"],
        "count": [10, 20, 15],
        "rate": [0.1, 0.2, 0.15],
    })
    opt = echarts_from_dataframe(df, chart_type="bar", x_col="group",
                                  y_cols=["count", "rate"], title="t")
    assert "series" in opt and len(opt["series"]) == 2
    assert opt["xAxis"]["data"] == ["A", "B", "C"]
    assert opt["yAxis"]["type"] == "value"
    assert opt["legend"]["data"] == ["count", "rate"]
    assert opt["series"][0]["type"] == "bar"
    assert opt["series"][0]["data"] == [10.0, 20.0, 15.0]


def test_line_smooth_and_stack() -> None:
    df = pd.DataFrame({
        "t": ["d1", "d2", "d3", "d4"],
        "a":  [1, 2, 3, 4],
        "b":  [4, 3, 2, 1],
    })
    opt = echarts_from_dataframe(df, chart_type="line", x_col="t",
                                  y_cols=["a", "b"], stack=True, smooth=True)
    assert opt["series"][0]["type"] == "line"
    assert opt["series"][0].get("stack") == "total"
    assert opt["series"][0].get("smooth") is True


def test_scatter_pairs() -> None:
    df = pd.DataFrame({
        "x": [1.0, 2.0, 3.0],
        "y": [2.0, 4.0, 6.0],
    })
    opt = echarts_from_dataframe(df, chart_type="scatter", x_col="x", y_cols=["y"])
    s = opt["series"][0]
    assert s["type"] == "scatter"
    assert s["data"] == [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]]
    assert opt["xAxis"]["type"] == "value"


def test_boxplot_groups() -> None:
    df = pd.DataFrame({
        "grp": ["A", "A", "B", "B", "B"],
        "val": [1.0, 3.0, 2.0, 4.0, 6.0],
    })
    opt = echarts_from_dataframe(df, chart_type="boxplot", x_col="grp", y_cols=["val"])
    assert opt["xAxis"]["data"] == ["A", "B"]
    assert len(opt["series"][0]["data"]) == 2
    # Each stat tuple has length 5
    for stats in opt["series"][0]["data"]:
        assert len(stats) == 5


def test_pie_aggregates_by_x() -> None:
    df = pd.DataFrame({
        "cat": ["a", "a", "b", "c"],
        "n":   [1,    2,   3,   4],
    })
    opt = echarts_from_dataframe(df, chart_type="pie", x_col="cat", y_cols=["n"])
    series = opt["series"][0]
    assert series["type"] == "pie"
    values = {item["name"]: item["value"] for item in series["data"]}
    assert values["a"] == 3.0
    assert values["b"] == 3.0
    assert values["c"] == 4.0


def test_find_markdown_tables_pipe_format() -> None:
    text = (
        "Some intro\n"
        "| col1 | col2 |\n"
        "| --- | --- |\n"
        "| a | 1 |\n"
        "| b | 2 |\n"
        "\n"
        "After table prose\n"
    )
    tables = find_markdown_tables(text)
    assert len(tables) == 1
    assert "| col1 | col2 |" in tables[0]
    assert "| --- |" in tables[0]


def test_find_markdown_tables_multiple() -> None:
    text = (
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
        "some text\n\n"
        "| x | y |\n| :-: | :-: |\n| 9 | 8 |\n"
    )
    tables = find_markdown_tables(text)
    assert len(tables) == 2
