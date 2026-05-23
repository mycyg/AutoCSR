"""Per-dictionary loaders.

All loaders implement the ``BaseLoader`` contract from ``app.coding.loaders.base``:

    loaded: bool
    n_codes: int
    info() -> SystemInfo
    search(term, top_k) -> list[CodingCandidate]
    get(code) -> CodingResult | None
"""
from app.coding.loaders.atc import ATCLoader  # noqa: F401
from app.coding.loaders.base import BaseLoader  # noqa: F401
from app.coding.loaders.icd10 import ICD10Loader  # noqa: F401
from app.coding.loaders.loinc_minimal import LOINCLoader  # noqa: F401
from app.coding.loaders.meddra import MedDRALoader  # noqa: F401
from app.coding.loaders.snomed import SNOMEDLoader  # noqa: F401
from app.coding.loaders.whodrug import WHODrugLoader  # noqa: F401
