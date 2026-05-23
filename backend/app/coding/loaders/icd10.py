"""ICD-10 loader (CC0 core, bundled)."""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


class ICD10Loader(BaseLoader):
    system_id = "ICD10"
    name = "ICD-10 (CC0 core subset)"
    version = "WHO ICD-10 2019 public release"
    source = "https://icd.who.int/browse10/"
    license = "CC0-1.0"
    notes = "Bundled CC0 subset of common diagnoses; full WHO release available from icd.who.int"

    def _do_load(self) -> None:
        here = Path(__file__).resolve().parent.parent / "data" / "icd10_simple.csv"
        if not here.exists():
            return
        self._ingest_rows(self._load_csv(here))
