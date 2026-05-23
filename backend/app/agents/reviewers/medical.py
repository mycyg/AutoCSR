"""Medical reviewer (M16).

Cross-checks AE narratives, dosing & ConMed interactions against the
processed dataset using the sandbox. Issues surfaced:

  * AE term mentioned in draft but absent from ADAE.AETERM
  * ConMed interaction flag never narrated when ADCM rows count is high
  * Dose mentioned in draft inconsistent with EXSTDOSE / EXSTDOSU values
  * Serious AE count in body deviates from ADAE.AESER='Y' tally

Defensive: if processed parquet files are missing the reviewer still
emits at least one info-level placeholder so the UI lights up.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.config import data_dir
from app.report.store import list_drafts
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.review import CheckerStatus, Issue, IssueLocation, ReviewResult

logger = logging.getLogger("autocsr.agents.reviewers.medical")


class MedicalReviewer(BaseAgent):
    name = "MedicalReviewer"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        pid = agent_input.project_id
        t0 = time.time()
        issues: list[Issue] = []
        drafts = list_drafts(pid)
        body_all = "\n\n".join(d.markdown or "" for d in drafts)

        adae = _load_dataset(pid, "ADAE")
        adcm = _load_dataset(pid, "ADCM")

        # 1) AE terms in drafts that do not appear in ADAE.AETERM
        if adae is not None and "AETERM" in adae.columns:
            ae_terms = set(str(x).strip() for x in adae["AETERM"].dropna().unique())
            # Cheap surface heuristic: surface unusual phrases with 2-6 ascii
            # tokens between markers "(AE: ...)" or quoted. To stay
            # deterministic & fast we cross-check the explicit AE-headed
            # mentions only — every literal "AE:" / "不良事件:" prefix.
            seen_pairs: set[tuple[str, str]] = set()
            for d in drafts:
                md = d.markdown or ""
                for m in re.finditer(
                    r"(?:AE\s*[:：]|不良事件\s*[:：])\s*([^\s，。;；]{2,40})", md,
                ):
                    term = m.group(1).strip(' "“”\'')
                    key = (d.node_id, term)
                    if key in seen_pairs:
                        continue
                    seen_pairs.add(key)
                    if term not in ae_terms and term not in body_all_stripped(ae_terms):
                        issues.append(Issue(
                            id=uuid.uuid4().hex[:10], severity="warn",
                            location=IssueLocation(
                                node_id=d.node_id,
                                char_range=(m.start(1), m.end(1)),
                            ),
                            message=f"AE 术语「{term}」在 ADAE.AETERM 中未找到",
                            suggestion="核对术语拼写或在 ADAE 中补 AETERM 记录。",
                            checker="medical",
                        ))
                        if len(issues) >= 8:
                            break
        else:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="info",
                location=IssueLocation(),
                message="未找到 ADAE 数据集，跳过 AE 术语交叉核对",
                checker="medical",
            ))

        # 2) Serious AE narrative vs tally
        if adae is not None and "AESER" in adae.columns:
            n_sae = int((adae["AESER"].astype(str).str.upper() == "Y").sum())
            # Look for any number followed by "SAE" / "严重不良事件"
            for m in re.finditer(
                r"(\d{1,4})\s*(?:例)?\s*(?:SAE|严重不良事件|serious adverse)",
                body_all, re.IGNORECASE,
            ):
                reported = int(m.group(1))
                if abs(reported - n_sae) > max(1, int(0.1 * max(reported, n_sae))):
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10], severity="error",
                        location=IssueLocation(),
                        message=f"叙述中 SAE 数 {reported} 与 ADAE.AESER='Y' 计数 {n_sae} 不一致",
                        suggestion="核对 SAE 定义与本期数据切片。",
                        checker="medical",
                    ))
                    break

        # 3) Dose consistency: if any "mg" mentioned, ensure it appears in EX dataset
        ex = _load_dataset(pid, "EX") or _load_dataset(pid, "ADEX")
        if ex is not None and any(c in ex.columns for c in ("EXDOSE", "EXSTDOSE")):
            col = "EXSTDOSE" if "EXSTDOSE" in ex.columns else "EXDOSE"
            try:
                doses = set(str(int(float(x))) for x in ex[col].dropna().unique()[:20])
            except Exception:
                doses = set()
            if doses:
                for m in re.finditer(r"(\d{1,4})\s*mg", body_all, re.IGNORECASE):
                    if m.group(1) not in doses:
                        issues.append(Issue(
                            id=uuid.uuid4().hex[:10], severity="warn",
                            location=IssueLocation(),
                            message=f"剂量 {m.group(1)} mg 在 EX 数据集 {col} 中未找到",
                            suggestion="检查给药方案描述或确认 EX 数据完整性。",
                            checker="medical",
                        ))
                        break

        # 4) ConMed interaction signal
        if adcm is not None and "CMTRT" in adcm.columns:
            n_cm = int(adcm["CMTRT"].notna().sum())
            if n_cm >= 20 and "合并用药" not in body_all and "concomitant" not in body_all.lower():
                issues.append(Issue(
                    id=uuid.uuid4().hex[:10], severity="warn",
                    location=IssueLocation(),
                    message=f"ADCM 含 {n_cm} 行合并用药记录，但报告正文未叙述",
                    suggestion="补充合并用药与潜在交互的临床解释。",
                    checker="medical",
                ))

        if not issues:
            issues.append(Issue(
                id=uuid.uuid4().hex[:10], severity="info",
                location=IssueLocation(),
                message="医学审稿未发现 AE / 剂量 / 合并用药明显冲突",
                checker="medical",
            ))
        status = CheckerStatus(
            name="medical", ok=True, issues_count=len(issues),
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


def body_all_stripped(s: set[str]) -> str:
    return " ".join(s)


def _load_dataset(pid: str, name: str):
    """Best-effort load of a processed dataset by stem name. Returns None
    on any failure."""
    pdir = data_dir() / "projects" / pid / "processed"
    if not pdir.exists():
        return None
    try:
        import pandas as pd
    except Exception:
        return None
    for path in pdir.glob("*"):
        if path.suffix.lower() not in (".parquet", ".csv"):
            continue
        stem_upper = path.stem.upper()
        if name.upper() not in stem_upper:
            continue
        try:
            if path.suffix.lower() == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path)
        except Exception:
            continue
    return None
