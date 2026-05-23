"""Section plan schemas (M10 — plan-first writing).

The "plan" step sits between outline and draft. For each leaf section we
ask the writer LLM to emit a short, editable outline of 5-8 bullet points
that capture *what* the section will say + which evidence each point will
lean on. The user reviews / edits these points and the refine step turns
them into the actual SectionDraft.

The plan is persisted at:

    data/projects/<pid>/plans/<node_id>.json

so the user can iterate over many points before paying for full draft
generation. Each PlanPoint carries enough metadata that the refine step
knows which Ref<...> codes and StatBlocks to weave back into the prose.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.report import LLMMeta


PointStatus = Literal["pending", "accepted", "edited"]


class PlanPoint(BaseModel):
    """One outline bullet inside a SectionPlan.

    ``text`` is the user-facing summary of what this paragraph will say
    (target 50-150 Chinese characters). ``evidence_hints`` are free-form
    pointers — usually mirror node.literature_refs / search terms — that
    the refine step should weave in. ``stat_refs_hint`` lists the exact
    StatBlock ``Ref<...>`` codes the point should cite verbatim.
    """
    id: str
    text: str
    evidence_hints: list[str] = Field(default_factory=list)
    stat_refs_hint: list[str] = Field(default_factory=list)
    status: PointStatus = "pending"


class SectionPlan(BaseModel):
    """The full plan for one outline leaf node."""
    node_id: str
    title: str = ""
    points: list[PlanPoint] = Field(default_factory=list)
    notes: str = ""                  # free-form writer-only notes
    version: int = 1
    created_at: datetime
    updated_at: datetime
    llm_meta: LLMMeta = Field(default_factory=LLMMeta)


class SectionPlanSummary(BaseModel):
    """Lightweight payload for the per-project plan list view."""
    node_id: str
    title: str
    n_points: int
    n_accepted: int
    version: int
    updated_at: datetime
