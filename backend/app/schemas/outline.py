"""Outline schemas — project-specific CSR table-of-contents tree.

An Outline is a versioned, mutable specialization of a Principle. The principle
provides the rigid section skeleton (id, title, requirements); the outline binds
each section to project-specific StatBlocks, literature blocks, and notes.

Status lifecycle on each node:
    pending  -> writing (M4) -> done -> editing (M5)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

NodeStatus = Literal["pending", "writing", "done", "editing"]


class OutlineNode(BaseModel):
    id: str                              # mirrors principle section id when present (e.g. "11.4.2.1")
    title: str
    principle_ref: str = ""              # Ref<principle_id>.S<section_id>
    level: int = 1                       # 1 = H1, 2 = H2, ...
    status: NodeStatus = "pending"
    stat_hints: list[str] = Field(default_factory=list)
    stat_refs: list[str] = Field(default_factory=list)        # bound StatBlock ref_code list
    literature_refs: list[str] = Field(default_factory=list)  # bound literature block ref_code list
    notes: str = ""
    project_specific: bool = False       # true if added by builder beyond principle skeleton
    children: list["OutlineNode"] = Field(default_factory=list)


OutlineNode.model_rebuild()


class Outline(BaseModel):
    project_id: str
    principle_id: str
    version: int = 1
    root_sections: list[OutlineNode] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    notes: list[str] = Field(default_factory=list)

    def walk(self) -> list[OutlineNode]:
        """Depth-first flatten — every node in the tree."""
        out: list[OutlineNode] = []

        def _w(n: OutlineNode) -> None:
            out.append(n)
            for c in n.children:
                _w(c)

        for s in self.root_sections:
            _w(s)
        return out

    def find(self, node_id: str) -> OutlineNode | None:
        for n in self.walk():
            if n.id == node_id:
                return n
        return None


class OutlineSummary(BaseModel):
    project_id: str
    principle_id: str
    version: int
    n_nodes: int
    n_with_stats: int
    n_with_lit: int
    created_at: datetime
    updated_at: datetime
