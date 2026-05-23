"""Coding result Pydantic schemas — shared by dictionary lookup, proposals, routes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CodingCandidate(BaseModel):
    """A single fuzzy-matched candidate from a dictionary search."""
    system: str
    code: str
    preferred_term: str
    hierarchy: list[str] = Field(default_factory=list)
    score: float = 0.0           # 0..1 confidence (higher = better)


class CodingResult(BaseModel):
    """A confirmed lookup result for a single (system, code) pair."""
    system: str
    code: str
    preferred_term: str
    hierarchy: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source: str = ""             # loader name / license / version snippet


class SystemInfo(BaseModel):
    id: str                      # canonical system id, eg "ICD10"
    name: str                    # human label, eg "ICD-10 (CC0 core)"
    version: str = ""
    source: str = ""             # data source / url
    license: str = ""            # eg "CC0-1.0" / "Commercial – user-supplied"
    available: bool = False      # whether data is loaded / configured
    n_codes: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
