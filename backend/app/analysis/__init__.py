"""Clinical statistical analysis modules.

All four sub-modules produce :class:`app.schemas.stats.StatBlock` instances. The
storage layer (:mod:`app.analysis.store`) persists them per-project and mirrors
each into the project's corpus index so writer agents (M4) can retrieve them.

Modules:
    descriptive  baseline / demographics tables
    inferential  group-comparison tests (t, Wilcoxon, chi2, Fisher)
    survival     Kaplan-Meier + Cox regression (lifelines)
    safety       AE summary by SOC/PT/severity/relatedness
    auto         one-shot router that detects ADaM-like parquets and dispatches
"""
from app.analysis import descriptive, inferential, survival, safety  # noqa: F401
from app.analysis.store import save, list_blocks, get, search, delete  # noqa: F401

__all__ = [
    "descriptive", "inferential", "survival", "safety",
    "save", "list_blocks", "get", "search", "delete",
]
