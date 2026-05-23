"""SNOMED CT loader.

SNOMED CT is a commercial dictionary. This loader **never** bundles SNOMED
content; ``coding.snomed_path`` in ``settings.yaml`` must point at a CSV or
an RF2 ``sct2_Description_*`` file.

A tiny synthetic sample ships for schema / CI testing only.
"""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


_SAMPLE: list[tuple[str, str, list[str]]] = [
    ("44054006", "Diabetes mellitus type 2 (disorder)", ["Disease", "Endocrine disorder"]),
    ("38341003", "Hypertensive disorder (disorder)", ["Disease", "Cardiovascular disorder"]),
    ("195967001", "Asthma (disorder)", ["Disease", "Respiratory disorder"]),
    ("13645005", "Chronic obstructive lung disease (disorder)", ["Disease", "Respiratory disorder"]),
    ("84114007", "Heart failure (disorder)", ["Disease", "Cardiovascular disorder"]),
    ("22298006", "Myocardial infarction (disorder)", ["Disease", "Cardiovascular disorder"]),
    ("230690007", "Cerebrovascular accident (disorder)", ["Disease", "Neurological disorder"]),
    ("363406005", "Malignant tumor of colon (disorder)", ["Disease", "Neoplasm"]),
    ("254837009", "Malignant neoplasm of breast (disorder)", ["Disease", "Neoplasm"]),
    ("254637007", "Non-small cell lung cancer (disorder)", ["Disease", "Neoplasm"]),
    ("70704007", "Pain (finding)", ["Finding", "Symptom"]),
    ("386661006", "Fever (finding)", ["Finding", "Symptom"]),
    ("422587007", "Nausea (finding)", ["Finding", "Symptom"]),
    ("271737000", "Anemia (disorder)", ["Disease", "Hematologic disorder"]),
    ("16114001", "Fracture of femur (disorder)", ["Disease", "Injury"]),
]


class SNOMEDLoader(BaseLoader):
    system_id = "SNOMED"
    name = "SNOMED CT"
    version = "Commercial – user supplied"
    source = "https://www.snomed.org/"
    license = "Affiliate – local NRC distribution"
    notes = ("Path is configured via settings.yaml -> coding.snomed_path. "
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
                csv = self._data_path / "snomed.csv"
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
                "Loaded synthetic SAMPLE only — configure coding.snomed_path "
                "to load a licensed SNOMED CT build."
            )
        return base
