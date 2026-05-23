"""Common scaffolding for dictionary loaders.

A loader owns a (potentially lazy) in-memory list of ``(code, term, hierarchy)``
tuples and provides fuzzy search via rapidfuzz.

CSV format expected by ``_load_csv``:
    code,term,hierarchy
where ``hierarchy`` is "|"-joined ancestor terms (may be empty).
"""
from __future__ import annotations

import csv
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from rapidfuzz import fuzz

from app.coding.schemas import CodingCandidate, CodingResult, SystemInfo


class BaseLoader(ABC):
    """Common entry points + lazy loading."""

    # Subclasses fill these in
    system_id: str = "UNKNOWN"
    name: str = "Unknown dictionary"
    version: str = ""
    source: str = ""
    license: str = "Unknown"
    notes: str = ""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._entries: list[tuple[str, str, list[str]]] = []
        self._by_code: dict[str, tuple[str, str, list[str]]] = {}

    # ------------------------------------------------------------------ public
    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def n_codes(self) -> int:
        return len(self._entries)

    def info(self) -> SystemInfo:
        # Trigger lazy load only if it's cheap (bundled loaders are);
        # commercial loaders override ``info`` to avoid surprise IO.
        self._ensure_loaded_safe()
        return SystemInfo(
            id=self.system_id, name=self.name, version=self.version,
            source=self.source, license=self.license,
            available=self.loaded and self.n_codes > 0,
            n_codes=self.n_codes, notes=self.notes,
        )

    def search(self, term: str, top_k: int = 5) -> list[CodingCandidate]:
        self._ensure_loaded_safe()
        if not self._entries or not term:
            return []
        q = term.strip().lower()
        scored: list[tuple[float, tuple[str, str, list[str]]]] = []
        for entry in self._entries:
            code, t, _ = entry
            t_l = t.lower()
            # Exact / startswith / fuzzy partial blend
            score = fuzz.partial_ratio(q, t_l) / 100.0
            if t_l == q:
                score = max(score, 1.0)
            elif t_l.startswith(q):
                score = max(score, 0.95)
            elif q in t_l:
                score = max(score, 0.85)
            if score >= 0.55:
                scored.append((score, entry))
        scored.sort(key=lambda x: (-x[0], x[1][0]))
        out: list[CodingCandidate] = []
        for s, (code, t, hier) in scored[:top_k]:
            out.append(CodingCandidate(
                system=self.system_id, code=code, preferred_term=t,
                hierarchy=list(hier), score=round(float(s), 3),
            ))
        return out

    def get(self, code: str) -> CodingResult | None:
        self._ensure_loaded_safe()
        e = self._by_code.get(code.strip().upper()) or self._by_code.get(code.strip())
        if not e:
            return None
        c, t, hier = e
        return CodingResult(
            system=self.system_id, code=c, preferred_term=t,
            hierarchy=list(hier), confidence=1.0,
            source=f"{self.name} ({self.license})",
        )

    # ------------------------------------------------------------ lazy loading
    def _ensure_loaded_safe(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                self._do_load()
            except Exception:
                # leave _entries empty — available=False is the user-visible signal
                self._entries = []
                self._by_code = {}
            self._loaded = True

    @abstractmethod
    def _do_load(self) -> None:
        """Populate ``self._entries`` (and ``self._by_code``)."""

    # ------------------------------------------------------------- shared util
    def _ingest_rows(self, rows: list[tuple[str, str, list[str]]]) -> None:
        self._entries = rows
        self._by_code = {}
        for r in rows:
            code = (r[0] or "").strip()
            self._by_code[code.upper()] = r
            self._by_code[code] = r

    @staticmethod
    def _load_csv(path: Path) -> list[tuple[str, str, list[str]]]:
        out: list[tuple[str, str, list[str]]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = (row.get("code") or "").strip()
                term = (row.get("term") or "").strip()
                hier_raw = (row.get("hierarchy") or "").strip()
                hier = [h for h in (hier_raw.split("|") if hier_raw else []) if h]
                if code and term:
                    out.append((code, term, hier))
        return out
