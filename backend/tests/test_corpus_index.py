"""Corpus index — ref encoding + grep search edge cases (M17)."""
from __future__ import annotations

import pytest

from app.corpus.index import (
    Block, add_block, fetch_ref, list_blocks, make_ref, parse_ref, search,
)


@pytest.fixture()
def temp_project(tmp_path, monkeypatch):
    from app import config as _cfg
    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    from app.corpus import index as _idx
    monkeypatch.setattr(_idx, "data_dir", lambda: tmp_path)
    return "corpus_test", tmp_path


def test_make_ref_for_literature_includes_pcp(temp_project):
    pid, _ = temp_project
    b = Block(project_id=pid, type="literature", page=3, col=2, para=1,
              text="An RCT showed efficacy.")
    bid = add_block(pid, b)
    block = fetch_ref(pid, f"Ref{bid}.P3.Col2.Para1")
    assert block is not None
    assert block.text.startswith("An RCT")


def test_parse_ref_distinguishes_kinds():
    assert parse_ref("Refabc123.P1.Col2.Para3")["kind"] == "literature"
    assert parse_ref("Refstat1.varAGE")["kind"] == "stat"
    assert parse_ref("Refp1.S11.4.2")["kind"] == "principle"
    assert parse_ref("Refnote1")["kind"] == "note"


def test_search_matches_partial_terms(temp_project):
    pid, _ = temp_project
    for txt in ["headache after dosing", "vomiting episode", "no AE recorded"]:
        add_block(pid, Block(
            project_id=pid, type="literature", page=1, col=1, para=1, text=txt,
        ))
    hits = search(pid, "headache", top_k=3)
    assert hits and hits[0].block.text.startswith("headache")


def test_make_ref_then_parse_roundtrip(temp_project):
    pid, _ = temp_project
    b = Block(project_id=pid, type="principle", page=1, col=1, para=1,
              text="ICH E3 requires...",
              meta={"section_id": "9.2.1", "principle_id": "ich_e3"})
    add_block(pid, b)
    ref = make_ref(b)
    parsed = parse_ref(ref)
    assert parsed is not None and parsed["kind"] == "principle"
