"""Marker schemas (M11 — colored annotations on draft text).

Markers are inline visual tags ('important', 'todo', 'question', 'risk')
attached to a character range inside a SectionDraft. They are stored on
the SectionDraft itself so version snapshots carry markers forward.

Default palette:
  important  -> #e6a23c (yellow)
  todo       -> #409eff (blue)
  question   -> #67c23a (green)
  risk       -> #f56c6c (red)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


MarkerType = Literal["important", "todo", "question", "risk"]


_DEFAULT_COLORS: dict[str, str] = {
    "important": "#e6a23c",
    "todo": "#409eff",
    "question": "#67c23a",
    "risk": "#f56c6c",
}


class Marker(BaseModel):
    id: str
    node_id: str
    type: MarkerType = "important"
    color: str = "#e6a23c"
    range: tuple[int, int] = (0, 0)
    note: str = ""
    created_at: datetime


def default_color(marker_type: str) -> str:
    return _DEFAULT_COLORS.get(marker_type, "#e6a23c")
