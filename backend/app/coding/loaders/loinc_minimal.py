"""LOINC loader (Regenstrief public domain core, bundled)."""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


class LOINCLoader(BaseLoader):
    system_id = "LOINC"
    name = "LOINC (CC0 minimal subset)"
    version = "Regenstrief LOINC 2.74 public domain core"
    source = "https://loinc.org/"
    license = "CC0-1.0"
    notes = "Bundled CC0 minimal subset of common laboratory & clinical observations (≥200)"

    def _do_load(self) -> None:
        here = Path(__file__).resolve().parent.parent / "data" / "loinc_minimal.csv"
        if not here.exists():
            return
        self._ingest_rows(self._load_csv(here))
