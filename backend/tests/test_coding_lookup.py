"""Coding dictionary edge cases (M17)."""
from __future__ import annotations

from app.coding import dictionary as coding


def test_suggest_system_for_column_meddra():
    assert coding.suggest_system_for_column("AETERM") == "MEDDRA"
    assert coding.suggest_system_for_column("ae_pt") == "MEDDRA"


def test_suggest_system_for_column_loinc():
    assert coding.suggest_system_for_column("LBTEST") == "LOINC"
    assert coding.suggest_system_for_column("lab_glucose") == "LOINC"


def test_suggest_system_returns_none_for_unrelated_column():
    assert coding.suggest_system_for_column("usubjid") is None
    assert coding.suggest_system_for_column("") is None


def test_lookup_empty_term_returns_empty():
    assert coding.lookup("ICD10", "") == []
    assert coding.lookup("ICD10", "   ") == []


def test_lookup_unknown_system_returns_empty():
    assert coding.lookup("DOES_NOT_EXIST", "headache") == []
