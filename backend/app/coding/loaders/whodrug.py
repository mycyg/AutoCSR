"""WHODrug loader.

WHODrug is a commercial dictionary licensed by Uppsala Monitoring Centre. This
loader **never** bundles WHODrug data; it expects the user to configure
``coding.whodrug_path`` in ``settings.yaml`` pointing at a CSV or a WHODrug
``dde.txt``-style flat file.

A tiny synthetic sample ships for schema / CI testing only.
"""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


_SAMPLE: list[tuple[str, str, list[str]]] = [
    ("000001-01-001", "ASPIRIN", ["Analgesics", "Salicylates"]),
    ("000001-02-001", "PARACETAMOL", ["Analgesics", "Anilides"]),
    ("000002-01-001", "AMOXICILLIN", ["Antibacterials", "Penicillins"]),
    ("000002-02-001", "AZITHROMYCIN", ["Antibacterials", "Macrolides"]),
    ("000003-01-001", "METFORMIN", ["Antidiabetics", "Biguanides"]),
    ("000003-02-001", "INSULIN GLARGINE", ["Antidiabetics", "Insulins"]),
    ("000004-01-001", "AMLODIPINE", ["Antihypertensives", "Calcium channel blockers"]),
    ("000004-02-001", "LISINOPRIL", ["Antihypertensives", "ACE inhibitors"]),
    ("000005-01-001", "ATORVASTATIN", ["Lipid modifying", "HMG-CoA reductase inhibitors"]),
    ("000005-02-001", "ROSUVASTATIN", ["Lipid modifying", "HMG-CoA reductase inhibitors"]),
    ("000006-01-001", "WARFARIN", ["Antithrombotics", "Vitamin K antagonists"]),
    ("000006-02-001", "APIXABAN", ["Antithrombotics", "Direct Xa inhibitors"]),
    ("000007-01-001", "OMEPRAZOLE", ["Acid-related", "PPI"]),
    ("000007-02-001", "ESOMEPRAZOLE", ["Acid-related", "PPI"]),
    ("000008-01-001", "SERTRALINE", ["Antidepressants", "SSRI"]),
    ("000008-02-001", "FLUOXETINE", ["Antidepressants", "SSRI"]),
]


class WHODrugLoader(BaseLoader):
    system_id = "WHODRUG"
    name = "WHODrug Global (UMC)"
    version = "Commercial – user supplied"
    source = "https://www.who-umc.org/whodrug/"
    license = "Commercial – UMC subscription required"
    notes = ("Path is configured via settings.yaml -> coding.whodrug_path. "
             "A small synthetic sample is bundled for schema/CI testing only.")

    def __init__(self, data_path: str | Path | None = None) -> None:
        super().__init__()
        self._data_path: Path | None = Path(data_path) if data_path else None
        self._using_sample = False

    def set_data_path(self, path: str | Path | None) -> None:
        with self._lock:
            self._data_path = Path(path) if path else None
            self._loaded = False
            self._using_sample = False
            self._entries = []
            self._by_code = {}

    def _do_load(self) -> None:
        rows: list[tuple[str, str, list[str]]] = []
        if self._data_path and self._data_path.exists():
            if self._data_path.is_file() and self._data_path.suffix.lower() == ".csv":
                rows = BaseLoader._load_csv(self._data_path)
            elif self._data_path.is_dir():
                csv = self._data_path / "whodrug.csv"
                if csv.exists():
                    rows = BaseLoader._load_csv(csv)
        if rows:
            self._using_sample = False
            self._ingest_rows(rows)
            return
        self._using_sample = True
        self._ingest_rows([(c, t, h) for c, t, h in _SAMPLE])

    def info(self):
        base = super().info()
        if self._using_sample:
            base.notes = (
                "Loaded synthetic SAMPLE only — configure coding.whodrug_path "
                "to load a licensed WHODrug build."
            )
        return base
