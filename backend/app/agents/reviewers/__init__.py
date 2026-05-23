"""Multi-reviewer expert agents (M16).

Three independent expert reviewers that run in parallel and merge their
findings. Each reviewer is an autonomous :class:`BaseAgent` so the
checker mock + retry decorator both apply uniformly.

The M10 single-agent :class:`ReviewerAgent` (3-checker structural
reviewer) is kept unchanged and exposed at the legacy ``/review``
endpoint. The new ``run_multi_review`` aggregates the three M16
experts at ``/multi_review``.
"""
from app.agents.reviewers.medical import MedicalReviewer  # noqa: F401
from app.agents.reviewers.multi import (  # noqa: F401
    MultiReviewResult, run_multi_review,
)
from app.agents.reviewers.regulatory import RegulatoryReviewer  # noqa: F401
from app.agents.reviewers.statistician import StatisticianReviewer  # noqa: F401
