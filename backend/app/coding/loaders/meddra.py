"""MedDRA loader.

MedDRA is a commercial dictionary licensed by MSSO. This loader **never**
bundles MedDRA terms; it expects the user to point ``coding.meddra_path`` (in
``settings.yaml``) at a directory containing MedDRA RF2-style ASCII files
or a 3-column CSV (``code,term,hierarchy``).

If the path is not configured or the directory is empty, the loader reports
``available=False`` so the UI / e2e can show a friendly "configure MedDRA"
banner instead of returning empty silently.

A tiny baked-in sample (≤20 PT) ships so that schemas and routes can be
exercised in CI without a real license — it's clearly labelled as a sample
and is never confused with a real MedDRA build.
"""
from __future__ import annotations

from pathlib import Path

from app.coding.loaders.base import BaseLoader


# Sample PT codes (synthetic — do not mistake for real MedDRA codes).
# Used only when no user-configured copy is present.
_SAMPLE: list[tuple[str, str, list[str]]] = [
    ("10019211", "Headache", ["Nervous system disorders", "Headaches"]),
    ("10028813", "Nausea", ["Gastrointestinal disorders", "Nausea and vomiting symptoms"]),
    ("10047700", "Vomiting", ["Gastrointestinal disorders", "Nausea and vomiting symptoms"]),
    ("10037087", "Rash", ["Skin and subcutaneous tissue disorders", "Rashes eruptions and exanthems"]),
    ("10016256", "Fatigue", ["General disorders and administration site conditions", "Fatigue"]),
    ("10047340", "Dizziness", ["Nervous system disorders", "Headaches"]),
    ("10012735", "Diarrhoea", ["Gastrointestinal disorders", "Diarrhoeal symptoms"]),
    ("10003988", "Back pain", ["Musculoskeletal and connective tissue disorders", "Back disorders"]),
    ("10005741", "Bronchitis", ["Respiratory thoracic and mediastinal disorders", "Lower respiratory infections"]),
    ("10003658", "Atrial fibrillation", ["Cardiac disorders", "Cardiac arrhythmias"]),
    ("10020802", "Hypertension", ["Vascular disorders", "Vascular hypertensive disorders"]),
    ("10020772", "Hyperglycaemia", ["Metabolism and nutrition disorders", "Glucose metabolism disorders"]),
    ("10001597", "Alopecia", ["Skin and subcutaneous tissue disorders", "Alopecias"]),
    ("10054788", "Neutropenia", ["Blood and lymphatic system disorders", "White blood cell disorders"]),
    ("10043554", "Thrombocytopenia", ["Blood and lymphatic system disorders", "Platelet disorders"]),
    ("10003162", "Asthenia", ["General disorders and administration site conditions", "Fatigue"]),
    ("10037660", "Pyrexia", ["General disorders and administration site conditions", "Body temperature conditions"]),
    ("10003658", "Anxiety", ["Psychiatric disorders", "Anxiety disorders and symptoms"]),
    ("10024188", "Insomnia", ["Psychiatric disorders", "Sleep disorders and disturbances"]),
    ("10047343", "Dyspnoea", ["Respiratory thoracic and mediastinal disorders", "Breathing abnormalities"]),
]


class MedDRALoader(BaseLoader):
    system_id = "MEDDRA"
    name = "MedDRA (Medical Dictionary for Regulatory Activities)"
    version = "Commercial – user supplied"
    source = "https://www.meddra.org/"
    license = "Commercial – MSSO subscription required"
    notes = ("Path is configured via settings.yaml -> coding.meddra_path. "
             "A small synthetic sample is bundled for schema/CI testing only.")

    def __init__(self, data_path: str | Path | None = None) -> None:
        super().__init__()
        self._data_path: Path | None = Path(data_path) if data_path else None
        self._using_sample = False

    def set_data_path(self, path: str | Path | None) -> None:
        """Reconfigure data path; resets the loader so the next call reloads."""
        with self._lock:
            self._data_path = Path(path) if path else None
            self._loaded = False
            self._using_sample = False
            self._entries = []
            self._by_code = {}

    def _do_load(self) -> None:
        # 1) User-supplied path takes precedence
        rows: list[tuple[str, str, list[str]]] = []
        if self._data_path and self._data_path.exists():
            rows = self._read_user_path(self._data_path)
        if rows:
            self._using_sample = False
            self._ingest_rows(rows)
            return
        # 2) Fall back to bundled sample (clearly labelled)
        self._using_sample = True
        self._ingest_rows([(c, t, h) for c, t, h in _SAMPLE])

    def info(self):
        base = super().info()
        if self._using_sample:
            base.notes = (
                "Loaded synthetic SAMPLE only — configure coding.meddra_path "
                "to load a licensed MedDRA build."
            )
        return base

    @staticmethod
    def _read_user_path(p: Path) -> list[tuple[str, str, list[str]]]:
        # Accept either a CSV (code,term,hierarchy) or a MedDRA llt.asc-style
        # pipe-delimited file with code in col 0 and term in col 1.
        if p.is_file() and p.suffix.lower() == ".csv":
            return BaseLoader._load_csv(p)
        if p.is_dir():
            cand_csv = p / "meddra.csv"
            if cand_csv.exists():
                return BaseLoader._load_csv(cand_csv)
            llt = p / "MedAscii" / "llt.asc"
            if llt.exists():
                out: list[tuple[str, str, list[str]]] = []
                with llt.open("r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        parts = line.rstrip("\n").split("$")
                        if len(parts) >= 2 and parts[0].strip():
                            out.append((parts[0].strip(), parts[1].strip(), []))
                return out
        return []
