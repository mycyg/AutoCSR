"""ATC loader (WHO ATC public release, CC0)."""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


class ATCLoader(BaseLoader):
    system_id = "ATC"
    name = "WHO ATC (CC0 core subset)"
    version = "WHOCC 2023 public release"
    source = "https://www.whocc.no/atc_ddd_index/"
    license = "CC0-1.0"
    notes = "Bundled CC0 subset of commonly prescribed drug codes (≥300)"

    def _do_load(self) -> None:
        here = Path(__file__).resolve().parent.parent / "data" / "atc_simple.csv"
        if not here.exists():
            return
        self._ingest_rows(self._load_csv(here))
