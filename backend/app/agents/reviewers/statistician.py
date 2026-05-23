"""Statistician reviewer (M16).

Inspects every section draft + StatBlock and surfaces issues about
statistical-method completeness:

  * absent normality / homoscedasticity statement around t-test / ANOVA
  * p-values reported without CI alongside
  * multiple-comparison correction never mentioned across subgroup blocks
  * StatBlock referenced from drafts without any narrative interpretation

The reviewer is deterministic + LLM-free so it works in mock mode and
across offline e2e. It uses regex heuristics on the existing markdown
(consistent with the M10 ConsistencyChecker pattern).
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.analysis.store import get as get_stat, list_blocks as list_stat_blocks
from app.report.store import list_drafts
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.review import CheckerStatus, Issue, IssueLocation, ReviewResult

logger = logging.getLogger("autocsr.agents.reviewers.statistician")


_PVAL_RE = re.compile(r"[Pp]\s*[=<>≈]\s*\d+(?:\.\d+)?")
_CI_RE = re.compile(r"(?:95\s*%\s*CI|置信区间|信赖区间)")
_NORMALITY_KEYWORDS = ("正态", "normality", "shapiro", "kolmogorov", "k-s")
_VARIANCE_KEYWORDS = ("方差齐性", "levene", "bartlett", "homoscedast")
_MULTI_KEYWORDS = ("bonferroni", "fdr", "holm", "校正", "adjust")
_PARAM_TESTS = ("t 检验", "t-test", "anova", "方差分析")


class StatisticianReviewer(BaseAgent):
    name = "StatisticianReviewer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        pid = agent_input.project_id
        t0 = time.time()
        issues: list[Issue] = []
        drafts = list_drafts(pid)
        stat_index = list_stat_blocks(pid)
        stat_ids = {s["id"] for s in stat_index}

        # Body text aggregated for cheap "has it been mentioned anywhere?"
        body_all = "\n\n".join(d.markdown or "" for d in drafts).lower()

        for d in drafts:
            md = (d.markdown or "")
            md_lc = md.lower()
            # 1. Param-test mentioned but no normality statement
            if any(t in md_lc for t in _PARAM_TESTS):
                if not any(k in md_lc for k in _NORMALITY_KEYWORDS):
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="warn",
                        location=IssueLocation(node_id=d.node_id),
                        message="使用了参数检验（t 检验 / ANOVA）但未给出正态性检验说明",
                        suggestion="补充 Shapiro-Wilk / K-S 检验或对应稳健性论证。",
                        checker="statistician",
                    ))
                if not any(k in md_lc for k in _VARIANCE_KEYWORDS):
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="info",
                        location=IssueLocation(node_id=d.node_id),
                        message="参数检验未提及方差齐性（Levene / Bartlett）",
                        suggestion="如适用，补一句方差齐性检验或采用 Welch 校正。",
                        checker="statistician",
                    ))
            # 2. p-value present without CI nearby
            for m in _PVAL_RE.finditer(md):
                window = md[max(0, m.start() - 80): m.end() + 80]
                if not _CI_RE.search(window):
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="warn",
                        location=IssueLocation(node_id=d.node_id,
                                               char_range=(m.start(), m.end())),
                        message=f"p 值 {m.group(0)} 附近未同时给出置信区间",
                        suggestion="对应效应量加 95% CI 以满足 ICH E3 报告完整性。",
                        checker="statistician",
                    ))
                    break  # one per section is enough

        # 3. Multiple-testing correction never mentioned but >= 2 subgroup/multitest blocks
        multi_count = sum(
            1 for s in stat_index
            if str(s.get("analysis_type") or "") in ("subgroup", "multitest")
        )
        if multi_count >= 2 and not any(k in body_all for k in _MULTI_KEYWORDS):
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="error",
                location=IssueLocation(),
                message=f"共有 {multi_count} 个亚组 / 多重检验块但报告中未出现校正方法说明",
                suggestion="补充 Bonferroni / FDR / Holm 校正或解释为何无需校正。",
                checker="statistician",
            ))

        # 4. StatBlock cited but no narrative interpretation
        for s in stat_index:
            ref = s.get("ref_code") or f"Ref{s.get('id')}"
            cited = any(ref in (d.markdown or "") for d in drafts)
            if cited:
                # check at least 80 chars of narrative around the ref
                for d in drafts:
                    if ref in (d.markdown or ""):
                        idx = d.markdown.find(ref)
                        window = d.markdown[max(0, idx - 80): idx + 80]
                        # 1 sentence ≈ ≥30 alnum/CJK chars
                        if len(re.sub(r"\s+", "", window)) < 60:
                            issues.append(Issue(
                                id=uuid.uuid4().hex[:10], severity="info",
                                location=IssueLocation(node_id=d.node_id),
                                message=f"StatBlock {ref} 被引用但缺少必要的结果解读",
                                suggestion="在引用前后补充 1-2 句结果解释 / 临床意义。",
                                checker="statistician",
                            ))
                            break

        # Always synthesise at least one informational finding so the UI
        # has something to render on a clean report.
        if not issues:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="info",
                location=IssueLocation(),
                message="统计审稿未发现重大缺陷；建议复查显著性界值的事先约定。",
                checker="statistician",
            ))

        status = CheckerStatus(
            name="statistician", ok=True, issues_count=len(issues),
            duration_ms=int((time.time() - t0) * 1000),
        )
        result = ReviewResult(
            project_id=pid,
            passed=not any(i.severity == "error" for i in issues),
            issues=issues,
            checkers=[status],
            created_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc),
        )
        return AgentOutput(ok=True, result=result.model_dump())
