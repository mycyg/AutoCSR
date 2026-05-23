"""Report draft schemas — outputs of M4 multi-agent writer.

A ReportDraft is the assembled output of all per-section :class:`SectionDraft`
objects. Each :class:`SectionDraft` is what a single writer_agent invocation
returns for one leaf section of the outline.

Citations are tracked at section granularity so the editor (M5) can resurface
the supporting evidence inline.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CitationKind = Literal["literature", "stat", "principle", "note"]


class CitationRef(BaseModel):
    """One citation embedded in a section draft.

    ``ref_code`` is the same canonical Ref<...> string emitted by
    ``app.corpus.index.make_ref`` so it can be resolved with ``fetch_ref``.
    ``type`` mirrors the corpus block type. ``locator`` is the bracketed
    in-text marker (e.g. ``[Ref<abc>.P1.Col1.Para1]`` or ``[T-AE-SOC]``)
    used in ``markdown`` so the editor can highlight it.
    """
    ref_code: str
    type: CitationKind
    locator: str = ""
    snippet: str = ""        # short evidence excerpt (≤120 chars) for tooltips


class LLMMeta(BaseModel):
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    via: str = ""           # "llm" / "mock" / "fallback"


class SectionDraft(BaseModel):
    node_id: str
    title: str = ""
    markdown: str = ""
    citations: list[CitationRef] = Field(default_factory=list)
    word_count: int = 0
    generated_at: datetime
    llm_meta: LLMMeta = Field(default_factory=LLMMeta)
    warnings: list[str] = Field(default_factory=list)
    status: Literal["draft", "harmonized", "error"] = "draft"
    # M11: colored inline annotations carried forward across versions.
    # Stored as plain dicts so older draft files without the field stay
    # loadable (Pydantic supplies a default empty list).
    markers: list[dict] = Field(default_factory=list)


class WriterTokens(BaseModel):
    input: int = 0
    output: int = 0


class ReportDraft(BaseModel):
    project_id: str
    outline_version: int = 0
    drafts: dict[str, SectionDraft] = Field(default_factory=dict)
    harmonized: bool = False
    generated_at: datetime
    total_tokens: WriterTokens = Field(default_factory=WriterTokens)
    total_words: int = 0
    leaves_total: int = 0
    leaves_done: int = 0
    leaves_errored: int = 0


class ReportStatus(BaseModel):
    """Lightweight status payload for the GET /report/status endpoint."""
    project_id: str
    outline_version: int | None = None
    leaves_total: int = 0
    leaves_done: int = 0
    leaves_errored: int = 0
    current_phase: str = "idle"     # idle | background | results | discussion | harmonize | done | error
    harmonized: bool = False
    total_tokens: WriterTokens = Field(default_factory=WriterTokens)
    total_words: int = 0
    last_event_at: datetime | None = None
    error: str | None = None
    sections: list[dict] = Field(default_factory=list)   # [{node_id,title,status,words,error?}]
