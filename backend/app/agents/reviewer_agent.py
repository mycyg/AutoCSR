"""Reviewer agent (M10).

Three parallel checkers run via ``asyncio.gather``:

  * :class:`ICHE3StructureChecker`  — verifies outline covers principle
    required sections; missing sections → error, extra sections → info.
  * :class:`ConsistencyChecker`    — extracts every number / p-value / CI
    / percentage from all section markdowns and cross-checks against
    StatBlock ``result_json``. Uses the sandbox to run the comparison so
    statistical heuristics stay containerised.
  * :class:`CitationValidator`     — confirms every ``Ref<...>`` in every
    SectionDraft resolves via ``fetch_ref``; flags nodes with
    ``stat_refs`` whose body never cites them.

One checker failing must never abort the others — we wrap each ``run``
in a try/except and emit a CheckerStatus instead.

Mock mode (``CSR_REVIEWER_MOCK=1``) substitutes deterministic stub
issues so e2e can assert "at least one inconsistency / broken ref" with
no LLM key configured.

Persistence:

  data/projects/<pid>/reviews/<yyyymmdd_hhmmss>.json    — full ReviewResult
  data/projects/<pid>/reviews/_ignored.json             — ignored issue ids
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
from app.analysis.store import get as get_stat, list_blocks as list_stat_blocks
from app.config import data_dir
from app.corpus.index import fetch_ref, parse_ref
from app.outline.store import load as load_outline
from app.principles import load_principle
from app.report.store import list_drafts
from app.sandbox.executor import execute_python
from app.schemas.agent import AgentInput, AgentOutput
from app.schemas.outline import Outline
from app.schemas.review import (
    CheckerStatus, Issue, IssueLocation, ReviewHistoryEntry, ReviewResult,
)
from app.server.ws import publish

logger = logging.getLogger("autocsr.agents.reviewer")


def _is_mock() -> bool:
    return os.environ.get("CSR_REVIEWER_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _lock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _reviews_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "reviews"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ignored_path(pid: str) -> Path:
    return _reviews_dir(pid) / "_ignored.json"


def load_ignored(pid: str) -> set[str]:
    p = _ignored_path(pid)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
    except Exception:
        pass
    return set()


def save_ignored(pid: str, ignored: set[str]) -> None:
    with _lock(pid):
        _ignored_path(pid).write_text(
            json.dumps(sorted(ignored), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _result_path(pid: str, created: datetime) -> Path:
    stamp = created.strftime("%Y%m%d_%H%M%S_%f")
    return _reviews_dir(pid) / f"{stamp}.json"


def save_review(result: ReviewResult) -> ReviewResult:
    payload = json.loads(result.model_dump_json())
    with _lock(result.project_id):
        _result_path(result.project_id, result.created_at).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # mirror as "latest"
        (_reviews_dir(result.project_id) / "latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return result


def load_latest(pid: str) -> ReviewResult | None:
    p = _reviews_dir(pid) / "latest.json"
    if not p.exists():
        return None
    try:
        return ReviewResult.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_history(pid: str) -> list[ReviewHistoryEntry]:
    out: list[ReviewHistoryEntry] = []
    for f in sorted(_reviews_dir(pid).glob("*.json")):
        if f.name in ("latest.json", "_ignored.json"):
            continue
        try:
            r = ReviewResult.model_validate_json(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        n_err = sum(1 for i in r.issues if i.severity == "error" and not i.ignored)
        n_warn = sum(1 for i in r.issues if i.severity == "warn" and not i.ignored)
        n_info = sum(1 for i in r.issues if i.severity == "info" and not i.ignored)
        out.append(ReviewHistoryEntry(
            created_at=r.created_at, passed=r.passed,
            n_errors=n_err, n_warns=n_warn, n_infos=n_info,
        ))
    return list(reversed(out))


def patch_issue(pid: str, issue_id: str, *, ignored: bool) -> bool:
    """Toggle ignored flag on the latest review snapshot + persist global
    ignored list. Returns True if the issue was found."""
    latest = load_latest(pid)
    if latest is None:
        return False
    found = False
    new_issues: list[Issue] = []
    for iss in latest.issues:
        if iss.id == issue_id:
            found = True
            new_issues.append(iss.model_copy(update={"ignored": ignored}))
        else:
            new_issues.append(iss)
    if not found:
        return False
    ig_set = load_ignored(pid)
    if ignored:
        ig_set.add(issue_id)
    else:
        ig_set.discard(issue_id)
    save_ignored(pid, ig_set)
    new = latest.model_copy(update={
        "issues": new_issues,
        "ignored_issue_ids": sorted(ig_set),
    })
    save_review(new)
    return True


# ---------------------------------------------------------------------------
# Checker 1 — ICH E3 structure
# ---------------------------------------------------------------------------

class _Checker:
    name: str = ""

    async def run(self, project_id: str) -> tuple[list[Issue], CheckerStatus]:
        raise NotImplementedError


class ICHE3StructureChecker(_Checker):
    name = "ich_e3_structure"

    async def run(self, project_id: str) -> tuple[list[Issue], CheckerStatus]:
        t0 = time.time()
        issues: list[Issue] = []
        outline = load_outline(project_id)
        if outline is None:
            return [], CheckerStatus(
                name=self.name, ok=False,
                error="no outline; cannot check structure",
                duration_ms=int((time.time() - t0) * 1000),
            )
        try:
            principle = load_principle(outline.principle_id)
        except Exception as e:  # noqa: BLE001
            return [], CheckerStatus(
                name=self.name, ok=False,
                error=f"cannot load principle {outline.principle_id}: {e}",
                duration_ms=int((time.time() - t0) * 1000),
            )
        outline_ids = {n.id for n in outline.walk()}
        required = [s for s in principle.flatten() if s.required]
        for sec in required:
            if sec.id not in outline_ids:
                issues.append(Issue(
                    id=uuid.uuid4().hex[:10],
                    severity="error",
                    location=IssueLocation(node_id=sec.id),
                    message=f"原则必填章节 {sec.id} 「{sec.title}」 未在大纲中出现",
                    suggestion="去大纲页添加该节，或解释为何裁剪。",
                    checker=self.name,
                ))
        # Extra sections (project_specific) → info
        principle_ids = {s.id for s in principle.flatten()}
        for n in outline.walk():
            if not n.id:
                continue
            if n.id not in principle_ids and not n.project_specific:
                # only flag if it's a leaf-level numeric id (e.g. "11.4.X.Y")
                # to avoid spamming for every project-specific subtree root
                if re.match(r"^\d+(\.\d+)+$", n.id):
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10],
                        severity="info",
                        location=IssueLocation(node_id=n.id),
                        message=f"大纲多出节 {n.id} 「{n.title}」 不在原则模板内",
                        suggestion="如属项目特有内容，可标记 project_specific=true。",
                        checker=self.name,
                    ))
        return issues, CheckerStatus(
            name=self.name, ok=True, issues_count=len(issues),
            duration_ms=int((time.time() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Checker 2 — Numeric consistency (sandbox-driven)
# ---------------------------------------------------------------------------

# 1) Percentages: "30.5%", "30%"
# 2) p-values: "p=0.03", "p<0.001", "P 值 0.04"
# 3) CIs: "95% CI 1.2-2.4" / "95% CI (1.2, 2.4)"
# 4) Bare numbers with units: "12.3 mg", "45 ml"
_NUM_PATTERNS = [
    (re.compile(r"(\d+(?:\.\d+)?)\s*%"), "pct"),
    (re.compile(r"[Pp][\s]*[=≈<>][\s]*(\d+(?:\.\d+)?)"), "pval"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(mg|kg|ml|mmHg|μg|ug)\b"), "unit"),
]


def _extract_numbers(text: str) -> list[tuple[str, str, int]]:
    """Return [(value, kind, char_offset), ...]"""
    out: list[tuple[str, str, int]] = []
    for pat, kind in _NUM_PATTERNS:
        for m in pat.finditer(text):
            out.append((m.group(1), kind, m.start()))
    return out


class ConsistencyChecker(_Checker):
    name = "consistency"

    async def run(self, project_id: str) -> tuple[list[Issue], CheckerStatus]:
        t0 = time.time()
        issues: list[Issue] = []
        drafts = list_drafts(project_id)
        stat_summaries = list_stat_blocks(project_id)

        if _is_mock():
            # Deterministic: scan drafts for any number that does NOT
            # appear in any stat block's markdown_table. Surface the
            # first 2 such collisions per draft as errors.
            stats_full: list[Any] = []
            for s in stat_summaries:
                sb = get_stat(project_id, s["id"])
                if sb is not None:
                    stats_full.append(sb)
            stat_text = " ".join(
                (sb.markdown_table or "") + " " + json.dumps(sb.result_json or {},
                                                              ensure_ascii=False)
                for sb in stats_full
            )
            for d in drafts:
                nums = _extract_numbers(d.markdown)
                # tolerance: if number substring not found anywhere, flag it
                seen = set()
                for val, kind, off in nums:
                    if not val or val in seen:
                        continue
                    seen.add(val)
                    if val not in stat_text:
                        issues.append(Issue(
                            id=uuid.uuid4().hex[:10],
                            severity="error",
                            location=IssueLocation(node_id=d.node_id,
                                                    char_range=(off, off + len(val) + 1)),
                            message=f"章节中出现的数值 {val} ({kind}) 在任何 StatBlock 中均未找到",
                            suggestion="核对原始统计输出，或补充 StatBlock 引用。",
                            checker=self.name,
                        ))
                        # only first inconsistency per draft is enough
                        break
            return issues, CheckerStatus(
                name=self.name, ok=True, issues_count=len(issues),
                duration_ms=int((time.time() - t0) * 1000),
            )

        # Non-mock path: generate sandbox python that does the same
        # check but with pandas; LLM-free deterministic code, runs in
        # the sandbox so any future enhancement (LLM-generated cross
        # checks) stays containerised.
        # Pack: drafts {node_id: markdown}, stats: [{id, markdown_table, result_json}]
        drafts_payload = {
            d.node_id: d.markdown for d in drafts
        }
        stats_payload: list[dict[str, Any]] = []
        for s in stat_summaries:
            sb = get_stat(project_id, s["id"])
            if sb is not None:
                stats_payload.append({
                    "id": sb.id,
                    "markdown_table": sb.markdown_table or "",
                    "result_json": sb.result_json or {},
                })

        # We embed the payload as a JSON literal inside the script (it's
        # the simplest portable way to ship structured input into the
        # sandbox). The AST guard already rejects open() outside the
        # sandbox dir, so the only safe route in is via the script body
        # or additional_data_paths (which expect on-disk files).
        payload_json = json.dumps(
            {"drafts": drafts_payload, "stats": stats_payload},
            ensure_ascii=False,
        )
        # Build the script with the payload inlined as a triple-quoted
        # raw string we then json.loads. Keep it terse to stay under
        # the AST line/size guardrails.
        code = (
            "import json, re\n"
            "_PAYLOAD = " + json.dumps(payload_json, ensure_ascii=False) + "\n"
            "data = json.loads(_PAYLOAD)\n"
            "drafts = data['drafts']\n"
            "stats = data['stats']\n"
            "stat_text = ' '.join((s.get('markdown_table') or '') + ' ' "
            "+ json.dumps(s.get('result_json') or {}, ensure_ascii=False) for s in stats)\n"
            "patterns = [\n"
            "  (re.compile(r'(\\d{1,3}(?:\\.\\d+)?)\\s*%'), 'pct'),\n"
            "  (re.compile(r'[Pp][\\s]*[=<>][\\s]*(\\d+(?:\\.\\d+)?)'), 'pval'),\n"
            "  (re.compile(r'(\\d+(?:\\.\\d+)?)\\s*(mg|kg|ml|mmHg|ug)\\b'), 'unit'),\n"
            "]\n"
            "issues = []\n"
            "for node_id, md in drafts.items():\n"
            "    md = md or ''\n"
            "    seen = set()\n"
            "    for pat, kind in patterns:\n"
            "        for m in pat.finditer(md):\n"
            "            val = m.group(1)\n"
            "            if val in seen: continue\n"
            "            seen.add(val)\n"
            "            if val not in stat_text:\n"
            "                issues.append({'node_id': node_id, 'value': val,\n"
            "                                'kind': kind, 'off': m.start()})\n"
            "                if len(issues) >= 50: break\n"
            "        if len(issues) >= 50: break\n"
            "    if len(issues) >= 50: break\n"
            "print('CONSISTENCY_RESULT=' + json.dumps(issues, ensure_ascii=False))\n"
        )

        def _run_sandbox() -> Any:
            return execute_python(project_id, code, timeout=30, mem_mb=512)

        res = await asyncio.to_thread(_run_sandbox)
        if res.error or res.exit_code != 0:
            return issues, CheckerStatus(
                name=self.name, ok=False,
                error=f"sandbox failed: {res.error or res.stderr[:160]}",
                duration_ms=int((time.time() - t0) * 1000),
            )
        # parse stdout
        m = re.search(r"CONSISTENCY_RESULT=(\[.*\])", res.stdout or "")
        if not m:
            return issues, CheckerStatus(
                name=self.name, ok=False,
                error=f"sandbox stdout did not contain marker; head={(res.stdout or '')[:120]}",
                duration_ms=int((time.time() - t0) * 1000),
            )
        try:
            findings = json.loads(m.group(1))
        except json.JSONDecodeError as je:
            return issues, CheckerStatus(
                name=self.name, ok=False,
                error=f"failed to parse sandbox JSON: {je}",
                duration_ms=int((time.time() - t0) * 1000),
            )
        for f in findings[:50]:
            off = int(f.get("off", 0))
            val = str(f.get("value") or "")
            issues.append(Issue(
                id=uuid.uuid4().hex[:10],
                severity="error",
                location=IssueLocation(
                    node_id=str(f.get("node_id") or ""),
                    char_range=(off, off + len(val) + 1),
                ),
                message=f"数值 {val} 在任何 StatBlock 中未找到对应",
                suggestion="比对原始统计输出或补充 StatBlock 引用。",
                checker=self.name,
            ))
        return issues, CheckerStatus(
            name=self.name, ok=True, issues_count=len(issues),
            duration_ms=int((time.time() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Checker 3 — Citation validity
# ---------------------------------------------------------------------------

_REF_PATTERN = re.compile(
    r"Ref[A-Za-z0-9_\-]+(?:\.(?:P\d+\.Col\d+\.Para\d+|var[A-Za-z0-9_\-]+|S[A-Za-z0-9_.\-]+))?"
)


class CitationValidator(_Checker):
    name = "citation"

    async def run(self, project_id: str) -> tuple[list[Issue], CheckerStatus]:
        t0 = time.time()
        issues: list[Issue] = []
        outline = load_outline(project_id)
        drafts = list_drafts(project_id)
        by_node: dict[str, Any] = {d.node_id: d for d in drafts}

        for d in drafts:
            md = d.markdown or ""
            for m in _REF_PATTERN.finditer(md):
                ref = m.group(0)
                ok = False
                parsed = parse_ref(ref)
                if parsed:
                    bid = parsed.get("bid") or parsed.get("pid") or ""
                    try:
                        block = fetch_ref(project_id, ref)
                    except Exception:
                        block = None
                    if block is not None:
                        ok = True
                    elif parsed["kind"] == "stat":
                        sb = get_stat(project_id, bid)
                        if sb is not None:
                            ok = True
                if not ok:
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10],
                        severity="error",
                        location=IssueLocation(
                            node_id=d.node_id,
                            char_range=(m.start(), m.end()),
                        ),
                        message=f"引用 {ref} 无法在 corpus / stats 中解析",
                        suggestion="删除该引用，或重新检索证据后补全。",
                        checker=self.name,
                    ))

        # Cross-check stat_refs coverage: outline node has stat_refs but
        # the draft body never cites them
        if outline is not None:
            for n in outline.walk():
                if not n.stat_refs:
                    continue
                d = by_node.get(n.id)
                if d is None:
                    continue
                md = d.markdown or ""
                missing = [r for r in n.stat_refs if r not in md]
                for r in missing:
                    issues.append(Issue(
                        id=uuid.uuid4().hex[:10],
                        severity="warn",
                        location=IssueLocation(node_id=n.id),
                        message=f"节 {n.id} 绑定的 StatBlock {r} 未在正文中被引用",
                        suggestion="在叙述对应数据时插入 [{}] 引用标记。".format(r),
                        checker=self.name,
                    ))

        return issues, CheckerStatus(
            name=self.name, ok=True, issues_count=len(issues),
            duration_ms=int((time.time() - t0) * 1000),
        )


# ---------------------------------------------------------------------------
# Parent ReviewerAgent — runs 3 checkers in parallel
# ---------------------------------------------------------------------------

class ReviewerAgent(BaseAgent):
    """Parent reviewer — fans out to 3 checkers concurrently and aggregates."""

    name = "Reviewer"

    def __init__(self) -> None:
        super().__init__()
        self.checkers: list[_Checker] = [
            ICHE3StructureChecker(),
            ConsistencyChecker(),
            CitationValidator(),
        ]

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        pid = agent_input.project_id
        await publish(pid, "review.start", {"checkers": [c.name for c in self.checkers]})

        async def _one(c: _Checker) -> tuple[list[Issue], CheckerStatus]:
            await publish(pid, "review.checker_start", {"name": c.name})
            try:
                iss, st = await c.run(pid)
            except Exception as e:  # noqa: BLE001
                st = CheckerStatus(name=c.name, ok=False, error=f"{type(e).__name__}: {e}")
                iss = []
            await publish(pid, "review.checker_done", {
                "name": c.name, "issues_count": st.issues_count,
                "ok": st.ok, "error": st.error,
            })
            return iss, st

        results = await asyncio.gather(*[_one(c) for c in self.checkers],
                                        return_exceptions=False)
        all_issues: list[Issue] = []
        all_status: list[CheckerStatus] = []
        for iss, st in results:
            all_issues.extend(iss)
            all_status.append(st)

        # Apply persisted ignore-list
        ig_set = load_ignored(pid)
        if ig_set:
            all_issues = [
                i.model_copy(update={"ignored": True}) if i.id in ig_set else i
                for i in all_issues
            ]

        passed = not any(
            i.severity == "error" and not i.ignored for i in all_issues
        )
        result = ReviewResult(
            project_id=pid,
            passed=passed,
            issues=all_issues,
            checkers=all_status,
            created_at=datetime.now(timezone.utc),
            ignored_issue_ids=sorted(ig_set),
        )
        save_review(result)
        # Invalidate alerts cache so the bar reflects the new review
        try:
            from app.server.routes.alerts import invalidate as _alerts_invalidate
            _alerts_invalidate(pid)
            await publish(pid, "alerts.updated", {"source": "review"})
        except Exception:
            pass
        await publish(pid, "review.done", {
            "passed": passed,
            "n_errors": sum(1 for i in all_issues if i.severity == "error" and not i.ignored),
            "n_warns": sum(1 for i in all_issues if i.severity == "warn" and not i.ignored),
            "n_infos": sum(1 for i in all_issues if i.severity == "info" and not i.ignored),
        })
        return AgentOutput(ok=True, result=result.model_dump())


async def run_review(project_id: str) -> ReviewResult:
    """Convenience entrypoint for routes / e2e."""
    agent = ReviewerAgent()
    ao = await agent.run(AgentInput(project_id=project_id))
    return ReviewResult.model_validate(ao.result)
