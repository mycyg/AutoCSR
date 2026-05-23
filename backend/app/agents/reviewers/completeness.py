"""Completeness reviewer (M17).

Cross-references the current outline against the principle YAML's
``required`` sections + ``stat_hints`` and the on-disk SectionDraft
state. Surfaces issues when:

* a principle section with ``required=True`` is absent from the outline;
* an outline node mapped to a principle section with ``stat_hints`` has
  no ``stat_refs`` bound;
* a leaf node still has empty markdown (``status='pending'`` or empty
  draft text).

Deterministic, LLM-free — drops into the MultiReviewResult as the 4th
checker via :mod:`app.agents.reviewers.multi`.
"""
from __future__ import annotations

import logging
import time
import uuid

from app.agents.base import BaseAgent
from app.outline import store as outline_store
from app.principles import load_principle
from app.report.store import load_draft
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.review import CheckerStatus, Issue, IssueLocation, ReviewResult

logger = logging.getLogger("autocsr.agents.reviewers.completeness")


class CompletenessReviewer(BaseAgent):
    name = "CompletenessReviewer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        pid = agent_input.project_id
        t0 = time.time()
        issues: list[Issue] = []

        outline = outline_store.load(pid)
        if outline is None:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="error",
                location=IssueLocation(),
                message="项目尚未生成 outline，无法校验完整性。",
                suggestion="先调用 /outline/build。",
                checker="completeness",
            ))
            return _wrap(pid, issues, t0)

        try:
            principle = load_principle(outline.principle_id)
        except Exception as e:
            logger.warning("principle load failed: %s", e)
            principle = None

        outline_ids = {n.id for n in outline.walk()}
        principle_by_id = {}
        if principle is not None:
            for sec in principle.flatten():
                principle_by_id[sec.id] = sec

            # 1) missing required sections
            for sec in principle.flatten():
                if sec.required and sec.id not in outline_ids:
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="error",
                        location=IssueLocation(extra={"section_id": sec.id}),
                        message=f"必填章节缺失: {sec.id} {sec.title}",
                        suggestion="在 outline 中补充该章节或调整 principle。",
                        checker="completeness",
                    ))

        # 2) stat_hints binding gap + 3) empty markdown on leaves
        for node in outline.walk():
            is_leaf = not node.children
            sec = principle_by_id.get(node.id) if principle_by_id else None

            if sec is not None and sec.stat_hints and not node.stat_refs:
                issues.append(Issue(
                    id=uuid.uuid4().hex[:10], severity="warn",
                    location=IssueLocation(node_id=node.id),
                    message=(
                        f"章节 {node.id} 在 principle 中有 stat_hints "
                        f"({', '.join(sec.stat_hints[:3])}) 但未绑定 stat_refs。"
                    ),
                    suggestion="在工作台为该章节绑定对应 StatBlock。",
                    checker="completeness",
                ))

            if is_leaf:
                draft = load_draft(pid, node.id)
                md = (draft.markdown or "").strip() if draft is not None else ""
                if not md:
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="error",
                        location=IssueLocation(node_id=node.id),
                        message=f"叶子章节 {node.id} 未生成正文。",
                        suggestion="运行 /report/generate 或手动编辑该章节。",
                        checker="completeness",
                    ))
                elif draft is not None and draft.status == "error":
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="warn",
                        location=IssueLocation(node_id=node.id),
                        message=f"叶子章节 {node.id} 生成失败 (status=error)。",
                        suggestion="检查 writer 日志后重跑该节。",
                        checker="completeness",
                    ))

        if not issues:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="info",
                location=IssueLocation(),
                message="完整性检查通过：所有必填章节与统计绑定齐全。",
                checker="completeness",
            ))

        return _wrap(pid, issues, t0)


def _wrap(pid: str, issues: list[Issue], t0: float) -> AgentOutput:
    import datetime as _dt
    status = CheckerStatus(
        name="completeness", ok=True, issues_count=len(issues),
        duration_ms=int((time.time() - t0) * 1000),
    )
    result = ReviewResult(
        project_id=pid,
        passed=not any(i.severity == "error" for i in issues),
        issues=issues,
        checkers=[status],
        created_at=_dt.datetime.now(_dt.timezone.utc),
    )
    return AgentOutput(ok=True, result=result.model_dump())
