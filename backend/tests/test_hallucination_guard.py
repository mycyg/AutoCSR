"""Reference-hallucination guard unit tests (M17)."""
from __future__ import annotations

import pytest

from app.corpus.index import Block, add_block
from app.safety.hallucination_guard import (
    extract_refs, mark_provenance_hallucinations, unique_refs,
    validate_references_against_corpus,
)
from app.schemas.report import Provenance


@pytest.fixture()
def temp_project(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    for module_path in ("app.corpus.index", "app.analysis.store",
                         "app.report.store"):
        try:
            mod = __import__(module_path, fromlist=["data_dir"])
            if hasattr(mod, "data_dir"):
                monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)
        except Exception:
            pass
    return "h_test", tmp_path


def test_extract_refs_picks_up_multiple_variants():
    md = "see Ref<abc>.P1.Col2.Para1 and Refxyz.var01 and [Refp9.S11.1]"
    refs = extract_refs(md)
    codes = [r[0] for r in refs]
    # The Ref<abc> form has an angle bracket id which our pattern intentionally
    # rejects — accept the bare RefXyz forms.
    assert "Refxyz.var01" in codes
    assert any(c.startswith("Refp9") for c in codes)


def test_unique_refs_deduplicates():
    md = "Refa1.P1.Col1.Para1 ... Refa1.P1.Col1.Para1"
    assert unique_refs(md) == ["Refa1.P1.Col1.Para1"]


def test_validate_references_emits_finding_for_missing_ref(temp_project):
    pid, _ = temp_project
    md = "according to Refmissing.P1.Col1.Para1 the drug works"
    findings = validate_references_against_corpus(md, pid)
    assert findings and findings[0].ref.startswith("Refmissing")


def test_validate_references_passes_when_ref_resolves(temp_project):
    pid, _ = temp_project
    b = Block(project_id=pid, type="literature", page=1, col=1, para=1,
              text="Drug X reduced AE rate.")
    bid = add_block(pid, b)
    md = f"see Ref{bid}.P1.Col1.Para1 for details"
    assert validate_references_against_corpus(md, pid) == []


def test_mark_provenance_hallucinations_flags_overlapping_range(temp_project):
    pid, _ = temp_project
    md = "claim Refnope.P1.Col1.Para1 was tested"
    findings = validate_references_against_corpus(md, pid)
    assert findings
    prov = [Provenance(range=(0, len(md)), source="ai")]
    updated = mark_provenance_hallucinations(prov, findings)
    assert updated[0].hallucination is True
