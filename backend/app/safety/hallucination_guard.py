"""Reference-hallucination guard (M17).

Scans drafted markdown for ``Ref<...>`` citations and verifies each one
resolves against the project's corpus / stat blocks / principle blocks.
When a reference cannot be found we emit a :class:`HallucinationFinding`
so the writer / chat-editor pipelines can mark the surrounding range
with ``Provenance.hallucination=True``.

The detector is deterministic, LLM-free and tolerant: it accepts every
``Ref<...>`` variant the corpus index emits today (literature with
``.P<page>.Col<col>.Para<para>``, stat with ``.var<col>``, principle
with ``.S<section>``, plain ``Ref<id>``) and also performs a permissive
prefix fallback for malformed-but-still-resolvable refs.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from pydantic import BaseModel, Field

# ``Ref<id>`` followed by optional dotted suffix (P/Col/Para, var, S)
# — id chars include the corpus index alphabet.
_REF_RE = re.compile(r"Ref([A-Za-z0-9_-]{2,40})(?:\.[A-Za-z0-9_.\-]+)?")


class HallucinationFinding(BaseModel):
    ref: str
    location_range: tuple[int, int] = (0, 0)
    severity: str = "error"          # error | warn | info
    suggestion: str | None = None
    node_id: str | None = None
    reason: str = "ref_not_found"


def extract_refs(markdown: str) -> list[tuple[str, int, int]]:
    """Return ``(ref_code, start, end)`` for every Ref<...> in markdown.

    De-duplication is NOT performed — callers may want the per-position
    spans for highlighting. Use :func:`unique_refs` if you only need the
    distinct codes.
    """
    if not markdown:
        return []
    out: list[tuple[str, int, int]] = []
    for m in _REF_RE.finditer(markdown):
        out.append((m.group(0), m.start(), m.end()))
    return out


def unique_refs(markdown: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for code, _s, _e in extract_refs(markdown):
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _resolve_ref(project_id: str, ref_code: str) -> bool:
    """Best-effort lookup. Returns True iff some backend confirms the ref."""
    # 1) Corpus index (literature/principle/note + parsed stat)
    try:
        from app.corpus.index import fetch_ref, parse_ref
        if fetch_ref(project_id, ref_code) is not None:
            return True
        # Some writer outputs trim trailing components ("Ref<bid>" or
        # "Ref<bid>.P1") — try the bare id as a prefix probe.
        parsed = parse_ref(ref_code)
        if parsed:
            bid = parsed.get("bid") or parsed.get("pid")
            if bid and fetch_ref(project_id, f"Ref{bid}") is not None:
                return True
    except Exception:
        pass

    # 2) Stat block store — refs are encoded as "Ref<stat_id>.var<col>"
    try:
        from app.analysis import store as stats_store
        bid_match = re.match(r"^Ref([A-Za-z0-9_-]+)", ref_code)
        if bid_match:
            bid = bid_match.group(1)
            if stats_store.get(project_id, bid) is not None:
                return True
            # ref_code may also embed full stat id like 'Ref<id>' only — already covered
    except Exception:
        pass

    # 3) Principle blocks ship globally under "_principles" project — try
    #    fetch_ref again on that pseudo project id.
    try:
        from app.corpus.index import fetch_ref
        if fetch_ref("_principles", ref_code) is not None:
            return True
    except Exception:
        pass

    return False


def validate_references_against_corpus(
    markdown: str,
    project_id: str,
    *,
    node_id: str | None = None,
) -> list[HallucinationFinding]:
    """Scan markdown and return a finding per unresolved reference.

    Each finding's ``location_range`` is the character span of the first
    occurrence of that ref so callers can shade / annotate that slice.
    """
    refs = extract_refs(markdown)
    if not refs:
        return []
    # Group spans by ref code; only emit the first span per code so
    # downstream UIs don't drown in duplicate red flags for the same
    # missing citation.
    first_span: dict[str, tuple[int, int]] = {}
    for code, s, e in refs:
        first_span.setdefault(code, (s, e))
    findings: list[HallucinationFinding] = []
    for code, span in first_span.items():
        if _resolve_ref(project_id, code):
            continue
        findings.append(HallucinationFinding(
            ref=code,
            location_range=span,
            severity="error",
            suggestion="Re-cite a verified Ref or remove the claim.",
            node_id=node_id,
            reason="ref_not_found",
        ))
    return findings


def mark_provenance_hallucinations(
    draft_provenance: list[Any],
    findings: Iterable[HallucinationFinding],
) -> list[Any]:
    """Best-effort: for every range overlapping a finding, set
    ``hallucination=True`` on the matching Provenance.

    We don't split provenance spans here — keeping the surgery minimal
    means older drafts loaded with extra keys still validate.
    """
    findings = list(findings)
    if not findings:
        return list(draft_provenance or [])
    out = []
    for p in draft_provenance or []:
        rng = getattr(p, "range", (0, 0)) or (0, 0)
        s, e = int(rng[0]), int(rng[1])
        overlap = any(not (f.location_range[1] < s or f.location_range[0] > e)
                       for f in findings)
        if overlap:
            try:
                out.append(p.model_copy(update={"hallucination": True}))
            except Exception:
                # Pydantic model lacks the field — set via model dump
                try:
                    d = p.model_dump()
                    d["hallucination"] = True
                    out.append(type(p).model_validate(d))
                except Exception:
                    out.append(p)
        else:
            out.append(p)
    return out


def project_scan(project_id: str) -> list[HallucinationFinding]:
    """Scan every persisted SectionDraft in a project and return the
    aggregated list of findings (each one tagged with the node_id)."""
    try:
        from app.report.store import list_drafts
    except Exception:
        return []
    out: list[HallucinationFinding] = []
    for draft in list_drafts(project_id):
        md = draft.markdown or ""
        for finding in validate_references_against_corpus(
            md, project_id, node_id=draft.node_id,
        ):
            out.append(finding)
    return out


__all__ = [
    "HallucinationFinding", "extract_refs", "unique_refs",
    "validate_references_against_corpus", "mark_provenance_hallucinations",
    "project_scan",
]
