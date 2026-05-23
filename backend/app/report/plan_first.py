"""Plan-first writing (M10).

Two-step authoring flow for a leaf section:

    make_plan(node, ctx)        — produce 5-8 PlanPoints (LLM, JSON-schema
                                  constrained or mock)
    refine_to_draft(plan, node) — expand plan into full SectionDraft using
                                  the existing writer pipeline

The plan persists at ``data/projects/<pid>/plans/<node_id>.json`` so the
user can edit it (PATCH route) before paying for the heavy refine step.

Mock mode (env ``CSR_PLAN_MOCK=1`` OR ``CSR_WRITER_MOCK=1``) emits a
deterministic stub plan with 5 points so e2e tests do not need an LLM key.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.base import AgentError, BaseAgent
from app.config import data_dir
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses_json as llm_responses_json
from app.report.store import save_draft
from app.report.writer_agent import (
    WriterContext, _load_evidence, _principle_requirements, write_section,
)
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.outline import OutlineNode
from app.schemas.plan import PlanPoint, SectionPlan
from app.schemas.report import LLMMeta, SectionDraft

logger = logging.getLogger("autocsr.report.plan_first")

_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _is_mock() -> bool:
    for key in ("CSR_PLAN_MOCK", "CSR_WRITER_MOCK"):
        if os.environ.get(key, "").lower() in ("1", "true", "yes"):
            return True
    return False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _plans_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "plans"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe(node_id: str) -> str:
    return node_id.replace("/", "_")


def _plan_path(pid: str, node_id: str) -> Path:
    return _plans_dir(pid) / f"{_safe(node_id)}.json"


def save_plan(pid: str, plan: SectionPlan) -> SectionPlan:
    """Persist plan to disk. Bumps ``updated_at``; caller decides on version."""
    payload = json.loads(plan.model_dump_json())
    with _lock(pid):
        _plan_path(pid, plan.node_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return plan


def load_plan(pid: str, node_id: str) -> SectionPlan | None:
    p = _plan_path(pid, node_id)
    if not p.exists():
        return None
    try:
        return SectionPlan.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_plans(pid: str) -> list[SectionPlan]:
    out: list[SectionPlan] = []
    for f in sorted(_plans_dir(pid).glob("*.json")):
        try:
            out.append(SectionPlan.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["points"],
    "properties": {
        "points": {
            "type": "array",
            "minItems": 3,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {
                    "text": {"type": "string", "minLength": 8},
                    "evidence_hints": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "stat_refs_hint": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "notes": {"type": "string"},
    },
}


def _build_plan_prompt(
    node: OutlineNode,
    stat_ev: list[dict[str, Any]],
    lit_ev: list[dict[str, Any]],
    requirements: list[str],
    language: str = "zh",
) -> tuple[str, str]:
    try:
        from app.i18n.loader import load_prompt
        sys = load_prompt("plan", language)
    except Exception:
        sys = (
            "你是临床研究报告章节策划师。任务：把一个章节拆成 5-8 个可独立成段的"
            "「写作点」(point)，每个 point 描述这一段要讲什么（50-150 字）。"
            "禁止编造 Ref 代码：stat_refs_hint 仅能来自给定的统计证据列表。"
        )
    parts: list[str] = []
    parts.append(f"## 章节\n- ID: {node.id}\n- 标题: {node.title}\n- 笔记: {node.notes or '(无)'}")
    if requirements:
        bullet = "\n".join(f"- {r}" for r in requirements[:10])
        parts.append(f"\n## 硬性要求\n{bullet}")
    if stat_ev:
        parts.append("\n## 可用统计证据 (Ref 代码请直接复制到 stat_refs_hint)")
        for s in stat_ev[:5]:
            parts.append(f"- [{s['ref_code']}] {s.get('title', '')}")
    if lit_ev:
        parts.append("\n## 可用文献证据")
        for l in lit_ev[:5]:
            snip = (l.get("text") or "")[:120].replace("\n", " ")
            parts.append(f"- [{l['ref_code']}]: {snip}")
    parts.append(
        "\n## 输出 JSON\n"
        '{"points": [{"text": "...", "evidence_hints": [...], "stat_refs_hint": [...]}, ...], '
        '"notes": "可选写作总体提示"}'
    )
    return sys, "\n".join(parts)


# ---------------------------------------------------------------------------
# Mock / LLM dispatch
# ---------------------------------------------------------------------------

def _mock_plan(node: OutlineNode, stat_ev: list[dict[str, Any]],
                lit_ev: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic 5-point stub plan."""
    sr = [s["ref_code"] for s in stat_ev[:2]]
    er = [l["ref_code"] for l in lit_ev[:2]]
    title = node.title or node.id
    base = [
        f"概述本节 {title} 的研究目的与范围，呼应章节硬性要求。",
        f"给出本节核心数据来源与分析人群定义，引用绑定的统计证据。",
        f"详细描述主要观察指标的统计结果及组间比较，附置信区间和 p 值。",
        f"讨论结果与既往文献的一致性、临床意义及潜在偏倚。",
        f"小结本节关键发现并指出对后续章节的衔接要点。",
    ]
    points: list[dict[str, Any]] = []
    for i, txt in enumerate(base):
        points.append({
            "text": txt,
            "evidence_hints": er[:1] if i in (2, 3) and er else [],
            "stat_refs_hint": sr[:1] if i in (1, 2) and sr else [],
        })
    return {"points": points,
            "notes": f"mock plan for {node.id} (5 deterministic points)"}


async def _call_plan_llm(node: OutlineNode, stat_ev: list[dict[str, Any]],
                          lit_ev: list[dict[str, Any]],
                          requirements: list[str],
                          policy: _policy.LLMPolicy,
                          project_id: str,
                          language: str) -> tuple[dict[str, Any], LLMMeta]:
    sys_msg, user_msg = _build_plan_prompt(node, stat_ev, lit_ev, requirements, language)
    t0 = time.time()
    try:
        def _call() -> dict[str, Any]:
            return llm_responses_json(
                [{"role": "system", "content": sys_msg},
                 {"role": "user", "content": user_msg}],
                schema=_SCHEMA,
                timeout=policy.timeout,
                max_tokens=policy.max_tokens,
                temperature=policy.temperature,
                reasoning_effort=policy.reasoning_effort,
                project_id=project_id,
                caller_agent="planner",
            )
        raw = await asyncio.to_thread(_call)
    except (ArkError, Exception) as e:  # noqa: BLE001
        raise AgentError(f"plan LLM failed: {e}", cause=e)
    if not isinstance(raw, dict) or not raw.get("points"):
        raise AgentError(f"plan LLM returned invalid payload: {str(raw)[:160]}")
    meta = LLMMeta(
        model=policy.name,
        tokens_in=0,
        tokens_out=0,
        latency_ms=int((time.time() - t0) * 1000),
        via="llm",
    )
    return raw, meta


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PlanContext:
    """Optional knobs for ``make_plan``."""
    def __init__(self, *, extra_instructions: str = "",
                 max_points: int = 8) -> None:
        self.extra_instructions = extra_instructions
        self.max_points = max_points


async def make_plan(
    project_id: str,
    node: OutlineNode,
    ctx: PlanContext | None = None,
) -> SectionPlan:
    """Produce + persist a fresh SectionPlan for one outline leaf node."""
    ctx = ctx or PlanContext()
    stat_ev, lit_ev = _load_evidence(project_id, node)
    requirements = _principle_requirements(node)

    if _is_mock():
        payload = _mock_plan(node, stat_ev, lit_ev)
        meta = LLMMeta(via="mock")
    else:
        policy = _policy.writer_llm()
        try:
            from app.report.orchestrator import _load_project_language
            language = _load_project_language(project_id)
        except Exception:
            language = "zh"
        payload, meta = await _call_plan_llm(node, stat_ev, lit_ev,
                                              requirements, policy, project_id,
                                              language)

    points: list[PlanPoint] = []
    for raw_p in (payload.get("points") or [])[:ctx.max_points]:
        if not isinstance(raw_p, dict):
            continue
        text = str(raw_p.get("text") or "").strip()
        if not text:
            continue
        # clamp text length: 50-150 chars target, hard cap 250
        if len(text) > 250:
            text = text[:250].rstrip() + "…"
        points.append(PlanPoint(
            id=uuid.uuid4().hex[:8],
            text=text,
            evidence_hints=[str(x) for x in (raw_p.get("evidence_hints") or [])][:5],
            stat_refs_hint=[str(x) for x in (raw_p.get("stat_refs_hint") or [])][:5],
            status="pending",
        ))

    now = datetime.now(timezone.utc)
    # version monotonic: load existing if present
    existing = load_plan(project_id, node.id)
    version = (existing.version + 1) if existing else 1
    plan = SectionPlan(
        node_id=node.id,
        title=node.title,
        points=points,
        notes=str(payload.get("notes") or ""),
        version=version,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        llm_meta=meta,
    )
    save_plan(project_id, plan)
    return plan


def patch_plan(project_id: str, node_id: str, *,
                points: list[dict[str, Any]] | None = None,
                notes: str | None = None) -> SectionPlan | None:
    """Apply user edits to a stored plan. Returns updated plan."""
    plan = load_plan(project_id, node_id)
    if plan is None:
        return None
    new_points = plan.points
    if points is not None:
        new_points = []
        for raw in points:
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or uuid.uuid4().hex[:8])
            text = str(raw.get("text") or "").strip()
            if not text:
                continue
            status = str(raw.get("status") or "edited")
            if status not in ("pending", "accepted", "edited"):
                status = "edited"
            new_points.append(PlanPoint(
                id=pid,
                text=text[:250],
                evidence_hints=[str(x) for x in (raw.get("evidence_hints") or [])][:5],
                stat_refs_hint=[str(x) for x in (raw.get("stat_refs_hint") or [])][:5],
                status=status,  # type: ignore[arg-type]
            ))
    new_notes = notes if notes is not None else plan.notes
    updated = plan.model_copy(update={
        "points": new_points,
        "notes": new_notes,
        "updated_at": datetime.now(timezone.utc),
    })
    save_plan(project_id, updated)
    return updated


def _plan_to_extra_instructions(plan: SectionPlan) -> str:
    lines: list[str] = ["## 写作计划 (请严格按以下要点逐段展开，每点对应一段)"]
    for i, pt in enumerate(plan.points, 1):
        lines.append(f"{i}. {pt.text}")
        if pt.stat_refs_hint:
            lines.append(f"   - 引用统计证据: {', '.join(pt.stat_refs_hint)}")
        if pt.evidence_hints:
            lines.append(f"   - 参考线索: {', '.join(pt.evidence_hints[:3])}")
    if plan.notes:
        lines.append(f"\n## 计划备注\n{plan.notes}")
    return "\n".join(lines)


async def refine_to_draft(
    project_id: str,
    node: OutlineNode,
    plan: SectionPlan | None = None,
    *,
    base_ctx: WriterContext | None = None,
) -> SectionDraft:
    """Expand a stored (or supplied) plan into a SectionDraft.

    Delegates to the existing :func:`write_section` so all M9 tool-loop
    + mock fallbacks remain in effect.
    """
    plan = plan or load_plan(project_id, node.id)
    if plan is None:
        raise AgentError(f"no plan for node {node.id}; call make_plan first",
                          retryable=False)
    extra = _plan_to_extra_instructions(plan)
    ctx = base_ctx or WriterContext(project_id=project_id)
    # Stack extra_instructions so any caller override still wins
    if ctx.extra_instructions:
        ctx = ctx.model_copy(update={
            "extra_instructions": f"{ctx.extra_instructions}\n\n{extra}",
        })
    else:
        ctx = ctx.model_copy(update={"extra_instructions": extra})
    draft = await write_section(project_id, node, ctx)
    # Tag warnings with the plan version so review can correlate
    new_warnings = list(draft.warnings or [])
    new_warnings.append(f"plan_v{plan.version}")
    draft = draft.model_copy(update={"warnings": new_warnings})
    save_draft(project_id, draft)
    return draft


# ---------------------------------------------------------------------------
# BaseAgent wrappers (so logging stays uniform)
# ---------------------------------------------------------------------------

class PlanAgent(BaseAgent):
    """``payload`` carries OutlineNode dict + optional PlanContext."""

    name = "Planner"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        node_raw = payload.get("node")
        if not node_raw:
            raise AgentError("missing payload.node", retryable=False)
        try:
            node = OutlineNode.model_validate(node_raw)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"invalid OutlineNode: {e}", retryable=False)
        ctx_raw = payload.get("context") or {}
        ctx = PlanContext(
            extra_instructions=str(ctx_raw.get("extra_instructions") or ""),
            max_points=int(ctx_raw.get("max_points") or 8),
        )
        plan = await make_plan(agent_input.project_id, node, ctx)
        return AgentOutput(
            ok=True, result=plan.model_dump(),
            llm_meta=plan.llm_meta,
            meta={"node_id": plan.node_id, "version": plan.version},
        )


class RefineAgent(BaseAgent):
    """``payload`` carries OutlineNode dict; uses persisted plan."""

    name = "Refiner"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        payload = agent_input.payload or {}
        node_raw = payload.get("node")
        if not node_raw:
            raise AgentError("missing payload.node", retryable=False)
        try:
            node = OutlineNode.model_validate(node_raw)
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"invalid OutlineNode: {e}", retryable=False)
        draft = await refine_to_draft(agent_input.project_id, node)
        return AgentOutput(
            ok=draft.status != "error",
            result=draft.model_dump(),
            warnings=list(draft.warnings or []),
            llm_meta=draft.llm_meta,
            meta={"node_id": draft.node_id},
        )
