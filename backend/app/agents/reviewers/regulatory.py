"""Regulatory reviewer (M16).

Performs content-level compliance check against ICH E3 / FDA / NMPA
expected disclosures. M10 ICHE3StructureChecker is *structural* (does
the outline have the section?); this reviewer asks "does the body
actually say the thing the regulator needs to see?".

Per-jurisdiction checklist (kept compact; community can extend):

  * ICH E3 §6.3   — informed consent statement must be in 6.3 or 9.1
  * ICH E3 §10.2  — exposure to study treatment (compliance + dosing)
  * FDA           — financial disclosure of investigators
  * NMPA          — 中文知情同意书审查 + 伦理委员会批件号
  * NMPA          — 主要研究者签字栏 (signature page)
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.agents.base import BaseAgent
from app.report.store import list_drafts
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.review import CheckerStatus, Issue, IssueLocation, ReviewResult

logger = logging.getLogger("autocsr.agents.reviewers.regulatory")


@dataclass(frozen=True)
class _Rule:
    id: str
    jurisdiction: str       # 'ICH' | 'FDA' | 'NMPA'
    severity: str           # 'error' | 'warn' | 'info'
    needle_re: re.Pattern
    scope_section: str | None        # None = any section
    message: str
    suggestion: str


def _r(p: str) -> re.Pattern:
    return re.compile(p, re.IGNORECASE)


_RULES: tuple[_Rule, ...] = (
    _Rule("ich-consent", "ICH", "error",
          _r(r"知情同意|informed consent"), "9",
          "ICH E3 要求第 9.1 / 6.3 节明确披露知情同意流程",
          "在伦理与法规章节补一段知情同意书获取过程描述。"),
    _Rule("ich-exposure", "ICH", "warn",
          _r(r"暴露|exposure|累计剂量|cumulative dose"), "10",
          "ICH E3 §10.2 要求叙述研究治疗暴露情况",
          "补充每位受试者的暴露天数 / 累计剂量描述。"),
    _Rule("fda-fin-disc", "FDA", "warn",
          _r(r"financial disclosure|经济利益披露|利益冲突"), None,
          "FDA 通常要求主要研究者的经济利益披露",
          "在附录添加研究者经济利益披露表（21 CFR 54）。"),
    _Rule("nmpa-ethics", "NMPA", "error",
          _r(r"伦理委员会|ethics committee|IRB|批件"), "9",
          "NMPA 要求披露伦理委员会批件号 / 批准日期",
          "补充伦理委员会名称、批件编号与批准日期。"),
    _Rule("nmpa-pi-sign", "NMPA", "info",
          _r(r"主要研究者签字|principal investigator signature|签字页"), "16",
          "NMPA 要求 CSR 含主要研究者签字页",
          "在附录 16 末尾保留主要研究者签字栏。"),
)


class RegulatoryReviewer(BaseAgent):
    name = "RegulatoryReviewer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        pid = agent_input.project_id
        t0 = time.time()
        issues: list[Issue] = []
        drafts = list_drafts(pid)
        by_section: dict[str, str] = {d.node_id: (d.markdown or "") for d in drafts}
        body_all = "\n\n".join(by_section.values())

        for rule in _RULES:
            scope_text = body_all
            scope_node = None
            if rule.scope_section:
                # Match any node whose id starts with the scope chapter.
                scoped = [
                    (nid, md) for nid, md in by_section.items()
                    if nid.startswith(rule.scope_section + ".") or nid == rule.scope_section
                ]
                if scoped:
                    scope_node = scoped[0][0]
                    scope_text = "\n\n".join(md for _, md in scoped)
                else:
                    # The required chapter isn't even drafted yet
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10],
                        severity=rule.severity,  # type: ignore[arg-type]
                        location=IssueLocation(node_id=rule.scope_section),
                        message=f"[{rule.jurisdiction}] {rule.message}（第 {rule.scope_section} 节缺失）",
                        suggestion=rule.suggestion,
                        checker="regulatory",
                    ))
                    continue
            if rule.needle_re.search(scope_text):
                continue
            issues.append(Issue(
                id=uuid.uuid4().hex[:10],
                severity=rule.severity,  # type: ignore[arg-type]
                location=IssueLocation(node_id=scope_node),
                message=f"[{rule.jurisdiction}] {rule.message}",
                suggestion=rule.suggestion,
                checker="regulatory",
            ))

        if not issues:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="info",
                location=IssueLocation(),
                message="法规审稿未发现关键披露缺失",
                checker="regulatory",
            ))

        status = CheckerStatus(
            name="regulatory", ok=True, issues_count=len(issues),
            duration_ms=int((time.time() - t0) * 1000),
        )
        from datetime import datetime, timezone
        result = ReviewResult(
            project_id=pid,
            passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            checkers=[status],
            created_at=datetime.now(timezone.utc),
        )
        return AgentOutput(ok=True, result=result.model_dump())
