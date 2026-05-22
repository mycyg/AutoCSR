"""Analyst agent (M8) — natural language data Q&A.

Pipeline:

  1. Caller hands us ``{query, scope, project_id, parquet_paths?}``.
  2. We build a small "data dossier" — the schema (column / dtype / 5
     redacted samples) of every available parquet under the project's
     ``processed/`` directory. The dossier is small and PII columns are
     masked, so feeding it to the LLM stays safe.
  3. ``analyst_llm`` is asked to emit a JSON object:
         ``{plan, code, expected_output_type}``
     where ``code`` is a self-contained Python snippet the sandbox will run.
  4. Sandbox executes the code. We parse stdout for markdown tables and
     scan artifacts for PNGs and ``chart.json`` (the LLM writes plotly /
     ECharts JSON there so we can ship it to the frontend).
  5. Result becomes a ``StatBlock`` with ``analysis_type='custom'`` and
     persisted via :mod:`app.analysis.store` (auto-mirrors into corpus).

The agent emits WS events ``analyst.thinking / code_generated /
sandbox_running / done / error`` so the AnalyzeView can stream them.

Mock mode (``CSR_ANALYST_MOCK=1``) bypasses the LLM and synthesises a
deterministic snippet over the first parquet — gives the e2e test a stable
codepath when no LLM key is configured.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import AgentError, BaseAgent
from app.analysis.store import get as get_stat, list_blocks as list_stat_blocks, save as save_block
from app.config import data_dir
from app.llm import policy as _policy
from app.llm.ark_client import ArkError, responses_json as llm_responses_json
from app.observability.logger import get_logger
from app.report.chart_tools import find_markdown_tables
from app.sandbox.executor import SandboxResult, execute_python
from app.schemas.agent import AgentInput, AgentOutput, LLMMeta
from app.schemas.stats import StatBlock
from app.server.ws import publish


logger = get_logger("Analyst")


# ---------------------------------------------------------------------------
# Pydantic IO
# ---------------------------------------------------------------------------

class AnalystInput(BaseModel):
    """Validated input payload — what the route stuffs into ``AgentInput``."""
    query: str
    scope: str = "all"            # "all" | "stat_block:<id>" | "section:<node_id>"
    project_id: str = ""
    parquet_paths: list[str] = Field(default_factory=list)
    sandbox_timeout_s: int = 60
    sandbox_mem_mb: int = 1024


class AnalystOutput(BaseModel):
    stat_block: dict[str, Any]
    sandbox_run_id: str
    llm_meta: LLMMeta = Field(default_factory=LLMMeta)


# ---------------------------------------------------------------------------
# Data dossier (schema + redacted samples)
# ---------------------------------------------------------------------------

# Columns whose values must never leave the project; mirror cleansing's
# hash_pii defaults.
_PII_COL_TOKENS = (
    "name", "phone", "address", "email", "idcard", "id_number",
    "passport", "patient", "subjid", "usubjid", "dob",
)


def _is_pii(col_name: str) -> bool:
    n = col_name.lower()
    return any(tok in n for tok in _PII_COL_TOKENS)


def _redact_sample(values: list[Any], pii: bool) -> list[Any]:
    if not pii:
        return [v if v is None or isinstance(v, (int, float, str, bool)) else str(v)
                for v in values]
    return ["<redacted>" for _ in values]


def _profile_parquet(path: Path, *, sample_rows: int = 5) -> dict[str, Any]:
    """Return a small schema-only descriptor for one parquet (or csv)."""
    import pandas as pd  # noqa: PLC0415

    try:
        if path.suffix.lower() == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)
    except Exception as e:
        return {"path": str(path), "error": f"load_failed:{e}", "columns": []}
    cols_info: list[dict[str, Any]] = []
    head = df.head(sample_rows)
    for c in df.columns:
        cols_info.append({
            "name": c,
            "dtype": str(df[c].dtype),
            "n_null": int(df[c].isna().sum()),
            "samples": _redact_sample(head[c].tolist(), _is_pii(c)),
        })
    return {
        "path": str(path),
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": cols_info,
    }


def _discover_parquets(project_id: str) -> list[Path]:
    """List every processed parquet under the project."""
    proc = data_dir() / "projects" / project_id / "processed"
    if not proc.exists():
        return []
    files = sorted([p for p in proc.glob("*.parquet")])
    files.extend(sorted(p for p in proc.glob("*.csv")))
    return files


def _scope_stat_block(project_id: str, scope: str) -> dict[str, Any] | None:
    if not scope.startswith("stat_block:"):
        return None
    sid = scope.split(":", 1)[1]
    sb = get_stat(project_id, sid)
    if sb is None:
        return None
    return {
        "id": sb.id,
        "title": sb.title,
        "analysis_type": sb.analysis_type,
        "markdown_table": (sb.markdown_table or "")[:1200],
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan": {"type": "string", "minLength": 1},
        "code": {"type": "string", "minLength": 1},
        "expected_output_type": {
            "type": "string",
            "enum": ["table", "chart", "both"],
        },
    },
    "required": ["plan", "code", "expected_output_type"],
}


_SYSTEM_PROMPT = """你是临床数据分析师。用户用自然语言问数据，你必须：

1. 想一个简短计划（≤80字，中文）。
2. 写一段自包含 Python 代码，输出到 stdout 的 markdown 表格（用 df.to_markdown() 或 tabulate），
   并将任何图表存为本目录下的 PNG（matplotlib）或同时写一份 ECharts/Plotly JSON 到 ./chart.json。
3. 沙盒环境已经允许 import pandas / numpy / scipy / matplotlib / plotly / statsmodels / lifelines / sklearn / seaborn；
   禁止 import os/sys/subprocess/socket/pathlib/requests/httpx；禁止读项目目录之外的文件。
4. 代码必须读取下方列出的 parquet 路径（pd.read_parquet）。不要捏造列名，请严格基于 schema。
5. 若用户问对比/分布，倾向 boxplot 或分组 bar；若问 top-N，输出 top-N 表格。
6. 图表代码段最终必须显式 `plt.tight_layout(); plt.savefig('chart.png')`；
   如使用 plotly 则 `import plotly.io as pio; pio.write_image(fig, 'chart.png')` 并将 `pio.to_json(fig)` 写到 './chart.json'。
7. **输出严格 JSON**：{"plan": str, "code": str, "expected_output_type": "table|chart|both"}
"""


def _build_user_prompt(
    query: str,
    parquet_profiles: list[dict[str, Any]],
    stat_blocks: list[dict[str, Any]],
    scope_block: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    parts.append(f"## 用户问题\n{query}\n")
    parts.append("## 可用数据文件（每列含 dtype + 5 行样例，PII 已遮蔽）")
    for prof in parquet_profiles:
        if prof.get("error"):
            parts.append(f"- {prof['path']} (load_error: {prof['error']})")
            continue
        parts.append(f"\n### `{prof['path']}` — {prof.get('n_rows', '?')} rows × {prof.get('n_cols', '?')} cols")
        for c in prof.get("columns", [])[:60]:
            samp = c["samples"]
            samp_str = ", ".join(repr(s) for s in samp[:3])
            parts.append(f"  - `{c['name']}` ({c['dtype']}, nulls={c['n_null']}) e.g. {samp_str}")
    if stat_blocks:
        parts.append("\n## 已有 StatBlock 索引（可参考但不要直接当输入）")
        for sb in stat_blocks[:10]:
            parts.append(f"  - {sb.get('id')} · {sb.get('analysis_type')} · {sb.get('title')}")
    if scope_block:
        parts.append(f"\n## 用户限定 scope：StatBlock `{scope_block['id']}` — {scope_block['title']}")
        parts.append(scope_block["markdown_table"])
    parts.append("\n## 请输出 JSON")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Mock mode — deterministic stub for offline e2e
# ---------------------------------------------------------------------------

def _mock_plan(query: str, parquet_paths: list[Path]) -> dict[str, str]:
    if not parquet_paths:
        return {
            "plan": "mock: no parquet available — print fixed table",
            "code": "print('| col | val |\\n| --- | --- |\\n| mock | 1 |')",
            "expected_output_type": "table",
        }
    paths_repr = [repr(str(p).replace("\\", "/")) for p in parquet_paths]
    paths_list = ", ".join(paths_repr)
    # Detect whether the query is about a chart vs a table
    want_chart = any(w in query for w in ("画", "图", "boxplot", "plot", "chart", "趋势", "分布"))
    if want_chart:
        code = (
            "import pandas as pd\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            f"_paths = [{paths_list}]\n"
            "_df = None\n"
            "for _p in _paths:\n"
            "    _cand = pd.read_parquet(_p)\n"
            "    if _cand.select_dtypes('number').shape[1] > 0:\n"
            "        _df = _cand\n"
            "        break\n"
            "if _df is None:\n"
            "    _df = pd.read_parquet(_paths[0])\n"
            "num = _df.select_dtypes('number')\n"
            "if num.shape[1] == 0:\n"
            "    print('| info | val |\\n| --- | --- |\\n| numeric_cols | 0 |')\n"
            "else:\n"
            "    summary = num.describe().round(2)\n"
            "    print(summary.to_markdown())\n"
            "    ax = num.iloc[:, 0].plot(kind='box')\n"
            "    plt.tight_layout()\n"
            "    plt.savefig('chart.png')\n"
            "    print('chart_saved')\n"
        )
        return {
            "plan": "mock: 描述数值列分布并画 boxplot",
            "code": code,
            "expected_output_type": "both",
        }
    # Pick whichever parquet has a categorical column (ADAE-style)
    code = (
        "import pandas as pd\n"
        f"_paths = [{paths_list}]\n"
        "_df = None\n"
        "for _p in _paths:\n"
        "    _cand = pd.read_parquet(_p)\n"
        "    if _cand.select_dtypes(include=['object','category']).shape[1] > 0:\n"
        "        _df = _cand\n"
        "        break\n"
        "if _df is None:\n"
        "    _df = pd.read_parquet(_paths[0])\n"
        "cat = _df.select_dtypes(include=['object','category']).columns.tolist()\n"
        "if cat:\n"
        "    top = _df[cat[0]].astype(str).value_counts().head(5).reset_index()\n"
        "    top.columns = [cat[0], 'count']\n"
        "    print(top.to_markdown(index=False))\n"
        "else:\n"
        "    print(_df.head().to_markdown())\n"
    )
    return {
        "plan": "mock: 取首个分类列的 top-5 出现频率",
        "code": code,
        "expected_output_type": "table",
    }


def _is_mock() -> bool:
    return os.environ.get("CSR_ANALYST_MOCK", "").lower() in ("1", "true", "yes") \
        or os.environ.get("CSR_WRITER_MOCK", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

def _extract_chart_json(workdir: Path) -> dict[str, Any] | None:
    """Read ``chart.json`` if the snippet wrote one."""
    for cand in (workdir / "chart.json", workdir / "artifacts" / "chart.json"):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                return None
    return None


def _first_png(artifacts: list[str]) -> str | None:
    for a in artifacts:
        if a.lower().endswith(".png"):
            return a
    return None


def _shorten_title(query: str, limit: int = 30) -> str:
    q = (query or "").strip()
    if len(q) <= limit:
        return q or "数据问答"
    return q[:limit] + "…"


# ---------------------------------------------------------------------------
# Async LLM call (wraps sync responses_json in a thread)
# ---------------------------------------------------------------------------

async def _call_llm(system_msg: str, user_msg: str, policy: _policy.LLMPolicy) -> tuple[dict[str, Any], LLMMeta]:
    import asyncio

    def _go() -> dict[str, Any]:
        return llm_responses_json(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            _PLAN_SCHEMA,
            timeout=policy.timeout,
            max_tokens=policy.max_tokens,
            temperature=policy.temperature,
            reasoning_effort=policy.reasoning_effort,
        )

    t0 = time.time()
    parsed = await asyncio.to_thread(_go)
    latency_ms = int((time.time() - t0) * 1000)
    meta = LLMMeta(model=policy.name, latency_ms=latency_ms, via="llm")
    # responses_json returns the parsed JSON object directly (no tokens info
    # available without changing ark_client). Token counts left at 0; the
    # caller may patch them in if it has access to the raw response.
    return parsed, meta


# ---------------------------------------------------------------------------
# Persistent ask history
# ---------------------------------------------------------------------------

def _asks_path(project_id: str) -> Path:
    d = data_dir() / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "asks.jsonl"


def append_ask_history(project_id: str, entry: dict[str, Any]) -> None:
    p = _asks_path(project_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def list_ask_history(project_id: str) -> list[dict[str, Any]]:
    p = _asks_path(project_id)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    # Newest first
    out.reverse()
    return out


# ---------------------------------------------------------------------------
# Public agent
# ---------------------------------------------------------------------------

class AnalystAgent(BaseAgent):
    """LLM-driven sandbox-backed data Q&A agent."""

    name = "Analyst"

    async def _run(self, agent_input: AgentInput) -> AgentOutput:
        from app.analysis._common import new_stat_id, now_utc

        try:
            payload = AnalystInput.model_validate({
                **(agent_input.payload or {}),
                "project_id": agent_input.project_id,
            })
        except Exception as e:  # noqa: BLE001
            raise AgentError(f"invalid AnalystInput: {e}", retryable=False)

        pid = payload.project_id
        query = payload.query.strip()
        if not query:
            raise AgentError("query is required", retryable=False)

        await publish(pid, "analyst.thinking", {"query": query, "scope": payload.scope})

        parquet_paths = [Path(p) for p in (payload.parquet_paths or [])]
        if not parquet_paths:
            parquet_paths = _discover_parquets(pid)
        parquet_paths = [p for p in parquet_paths if p.exists()]

        # Build dossier
        profiles = [_profile_parquet(p) for p in parquet_paths[:8]]
        stat_idx = list_stat_blocks(pid)[:20]
        scope_block = _scope_stat_block(pid, payload.scope)

        # 1. LLM plan + code -------------------------------------------------
        llm_meta = LLMMeta()
        plan_obj: dict[str, Any]
        if _is_mock():
            plan_obj = _mock_plan(query, parquet_paths)
            llm_meta = LLMMeta(model="mock", via="mock")
        else:
            policy = _policy.analyst_llm()
            try:
                user_msg = _build_user_prompt(query, profiles, stat_idx, scope_block)
                plan_obj, llm_meta = await _call_llm(_SYSTEM_PROMPT, user_msg, policy)
            except (ArkError, Exception) as e:  # noqa: BLE001
                logger.warning("analyst.llm_failed", error=str(e)[:200])
                # Fallback to mock so the orchestrator stays alive
                plan_obj = _mock_plan(query, parquet_paths)
                llm_meta = LLMMeta(model="fallback", via="fallback")

        plan = str(plan_obj.get("plan") or "")[:600]
        code = str(plan_obj.get("code") or "").strip()
        expected = str(plan_obj.get("expected_output_type") or "table")
        if not code:
            raise AgentError("LLM returned empty code", retryable=False)

        await publish(pid, "analyst.code_generated", {
            "plan": plan, "code": code,
            "expected_output_type": expected,
        })

        # 2. Sandbox run -----------------------------------------------------
        import asyncio

        def _run_sandbox() -> SandboxResult:
            return execute_python(
                pid, code,
                timeout=payload.sandbox_timeout_s,
                mem_mb=payload.sandbox_mem_mb,
                additional_data_paths=[str(p) for p in parquet_paths],
            )

        await publish(pid, "analyst.sandbox_running", {"run_id": "(pending)"})
        sandbox_res = await asyncio.to_thread(_run_sandbox)
        await publish(pid, "analyst.sandbox_running", {
            "run_id": sandbox_res.run_id,
            "exit_code": sandbox_res.exit_code,
            "error": sandbox_res.error,
        })

        warnings: list[str] = []
        if sandbox_res.exit_code != 0 or sandbox_res.error:
            warnings.append(
                f"sandbox_error:{sandbox_res.error or sandbox_res.exit_code}",
            )

        # 3. Parse stdout + artifacts ---------------------------------------
        tables = find_markdown_tables(sandbox_res.stdout)
        md_table = tables[0] if tables else ""
        if not md_table and sandbox_res.stdout.strip():
            # If LLM printed non-table output, keep first 4 KB as text block
            md_table = sandbox_res.stdout.strip()[:4000]

        chart_json = _extract_chart_json(Path(sandbox_res.workdir))
        png_path = _first_png(sandbox_res.artifacts or [])

        # 4. Build + persist StatBlock --------------------------------------
        block = StatBlock(
            id=new_stat_id(),
            project_id=pid,
            analysis_type="custom",
            title=_shorten_title(query),
            params={
                "query": query,
                "scope": payload.scope,
                "expected_output_type": expected,
                "sandbox_run_id": sandbox_res.run_id,
                "sandbox_workdir": sandbox_res.workdir,
                "sandbox_exit_code": sandbox_res.exit_code,
                "sandbox_error": sandbox_res.error,
            },
            result_json={
                "query": query,
                "plan": plan,
                "sandbox_code": code,
                "chart_json": chart_json,
                "png_path": png_path,
                "stdout_tail": sandbox_res.stdout[-2000:],
                "stderr_tail": sandbox_res.stderr[-2000:],
            },
            markdown_table=md_table,
            source_files=[str(p) for p in parquet_paths],
            created_at=now_utc(),
            notes=warnings,
        )
        saved = await asyncio.to_thread(save_block, pid, block)

        # 5. Append ask history file
        history_entry = {
            "stat_id": saved.id,
            "ts": time.time(),
            "query": query,
            "scope": payload.scope,
            "sandbox_run_id": sandbox_res.run_id,
            "expected_output_type": expected,
            "ok": sandbox_res.exit_code == 0,
        }
        append_ask_history(pid, history_entry)

        await publish(pid, "analyst.done", {
            "stat_block_id": saved.id,
            "title": saved.title,
            "has_chart_json": chart_json is not None,
            "has_png": bool(png_path),
        })

        return AgentOutput(
            ok=sandbox_res.exit_code == 0,
            result=AnalystOutput(
                stat_block=json.loads(saved.model_dump_json()),
                sandbox_run_id=sandbox_res.run_id,
                llm_meta=llm_meta,
            ).model_dump(),
            warnings=warnings,
            llm_meta=llm_meta,
            meta={"stat_id": saved.id, "query": query},
        )


# ---------------------------------------------------------------------------
# Convenience callable for tool loop integration (M9)
# ---------------------------------------------------------------------------

async def run_analyst(
    project_id: str,
    query: str,
    *,
    scope: str = "all",
    parquet_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Run the analyst once and return its AgentOutput.result dict."""
    agent = AnalystAgent()
    inp = AgentInput(
        project_id=project_id,
        payload={
            "query": query,
            "scope": scope,
            "parquet_paths": list(parquet_paths or []),
        },
        meta={"caller": "run_analyst"},
    )
    try:
        out = await agent.run(inp)
    except AgentError as e:
        await publish(project_id, "analyst.error", {"msg": str(e)})
        raise
    return out.result or {}
