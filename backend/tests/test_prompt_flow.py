from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def test_plan_prompt_uses_i18n_template():
    from app.report.plan_first import _build_plan_prompt
    from app.schemas.outline import OutlineNode

    sys_msg, user_msg = _build_plan_prompt(
        OutlineNode(id="11.1", title="Safety"),
        stat_ev=[{"ref_code": "RefStat123", "title": "AE summary"}],
        lit_ev=[],
        requirements=["Summarize safety population"],
        language="en",
    )

    assert "CSR section planner" in sys_msg
    assert "Output schema-valid JSON only" in sys_msg
    assert "RefStat123" in user_msg


def test_protocol_importer_uses_responses_json(monkeypatch):
    captured: dict[str, object] = {}

    def fake_responses_json(messages, schema, **kw):
        captured["messages"] = messages
        captured["schema"] = schema
        captured["kw"] = kw
        return {
            "study_id": "ABC-123",
            "phase": "Phase 2",
            "indication": "hypertension",
            "treatment": "Drug A",
            "endpoints": ["SBP change"],
            "population": "Adults",
            "design_type": "randomized",
            "sample_size": 120,
            "extra_notes": "",
        }

    monkeypatch.setattr("app.llm.ark_client.responses_json", fake_responses_json)
    monkeypatch.setattr(
        "app.llm.policy.for_role",
        lambda role: SimpleNamespace(timeout=10, max_tokens=4000, reasoning_effort="medium"),
    )

    from app.ingestion.protocol_importer import _llm_extract

    meta = _llm_extract("Protocol No: ABC-123\nPhase 2 randomized trial", "p_prompt")

    assert meta is not None
    assert meta.study_id == "ABC-123"
    kw = captured["kw"]
    assert kw["project_id"] == "p_prompt"  # type: ignore[index]
    assert kw["caller_agent"] == "protocol_importer"  # type: ignore[index]


def test_report_store_sanitizes_windows_node_ids(tmp_path, monkeypatch):
    from app import config as _cfg
    from app.report import store
    from app.schemas.report import SectionDraft

    monkeypatch.setattr(_cfg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(store, "data_dir", lambda: tmp_path)

    draft = SectionDraft(
        node_id="..\\outside",
        title="Unsafe node",
        markdown="## Unsafe node\n\nBody",
        generated_at=datetime.now(timezone.utc),
    )
    store.save_draft("p_prompt", draft)

    assert store.load_draft("p_prompt", "..\\outside") is not None
    assert not (tmp_path / "projects" / "p_prompt" / "outside.json").exists()
    assert not (tmp_path / "projects" / "p_prompt" / "..\\outside.json").exists()
