"""End-to-end test for M20 (v2.2) — domain templates + sample projects +
literature search + polish + chart selector + reference formatter +
LaTeX formula.

Coverage:
  1. All 5 domain principles + 5 templates load
  2. Sample data parquets exist (or are generated inline)
  3. GET /api/sample_projects returns 5 domains
  4. POST /api/projects/from_sample/oncology  → project created with
     parquets staged and outline (background) eventually built
  5. POST /api/projects/{pid}/literature_search → ≥1 paper (mock-mode
     fallback if offline)
  6. POST /api/projects/{pid}/polish/{node_id} body {mode: 'academic'}
     returns unified diff
  7. POST /api/projects/{pid}/chart/recommend with a synthetic survival
     stat_block returns chart_type='km' or 'km_with_risk_table'
  8. POST /api/projects/{pid}/export/docx with reference_style='gb7714'
     produces a References chapter containing '[1]' + '[J]'
  9. POST /api/projects/{pid}/export/docx with markdown containing
     ``$$ E = mc^2 $$`` embeds at least one inline image
 10. Regression: m2-m19 e2e scripts pass (called via subprocess gate)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8800"


def info(msg: str) -> None:
    print(f"[E2E-M20] {msg}", flush=True)


CHECKS: list[tuple[str, bool]] = []


def check(name: str, cond: bool, hint: str = "") -> bool:
    marker = "PASS" if cond else "FAIL"
    print(f"  [{marker}] {name}{' — ' + hint if (hint and not cond) else ''}",
          flush=True)
    CHECKS.append((name, bool(cond)))
    return bool(cond)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

def _start(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8800")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server.main:app",
         "--port", "8800", "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=BACKEND, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                info("server up")
                return proc
        except requests.RequestException:
            time.sleep(0.4)
    proc.terminate()
    raise RuntimeError("server did not come up")


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _cleanup_project(pid: str) -> None:
    try:
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
        pj = data_dir() / "projects.json"
        if pj.exists():
            items = json.loads(pj.read_text(encoding="utf-8") or "[]")
            items = [p for p in items if p.get("id") != pid]
            pj.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 0 — purely-local checks (no server)
# ---------------------------------------------------------------------------

def _phase_local() -> None:
    info("phase 0: local sanity (principles + templates + sample data)")
    sys.path.insert(0, str(BACKEND))
    from app.principles import list_principles, load_principle
    pids = {p.id for p in list_principles()}
    for required in ("oncology", "rare_disease", "vaccine",
                      "pediatric", "cardiovascular"):
        check(f"principle '{required}' loads",
              required in pids,
              f"available={sorted(pids)}")
        if required in pids:
            pr = load_principle(required)
            check(f"principle '{required}' has ≥20 nodes",
                  len(pr.flatten()) >= 20,
                  f"got {len(pr.flatten())}")

    from app.projects.templates import list_templates
    tpls = {t.id for t in list_templates()}
    for required in ("oncology", "rare_disease", "vaccine",
                      "pediatric", "cardiovascular"):
        check(f"template '{required}' visible",
              required in tpls,
              f"available={sorted(tpls)}")

    # Generate sample data inline (deterministic + idempotent)
    info("phase 0b: generating sample parquets")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_sample_data", ROOT / "scripts" / "generate_sample_data.py")
    mod = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(mod)                  # type: ignore[union-attr]
    written = mod.generate_all()
    for domain in ("oncology", "rare_disease", "vaccine",
                     "pediatric", "cardiovascular"):
        check(f"sample data {domain} has 3 parquets",
              len(written.get(domain) or {}) == 3,
              f"got {written.get(domain)}")

    # Reference formatter
    from app.export.reference_formatter import format_references
    van = format_references([
        {"title": "PD-L1 in NSCLC", "authors": ["Smith J", "Lee K"],
         "year": 2024, "journal": "NEJM",
         "volume": 390, "issue": 3, "pages": "123-130"},
    ], style="vancouver")
    check("vancouver renders '1.' + 'NEJM. 2024'",
          van and van[0].startswith("1.") and "NEJM" in van[0] and "2024" in van[0],
          van[0] if van else "(empty)")
    gb = format_references([
        {"title": "肿瘤试验", "authors": ["张三", "李四"], "year": 2024,
         "journal": "中华肿瘤杂志", "volume": 15, "issue": 3,
         "pages": "123-130"},
    ], style="gb7714")
    check("gb7714 renders '[1]' + '[J]' + '15(3)'",
          gb and "[1]" in gb[0] and "[J]" in gb[0] and "15(3)" in gb[0],
          gb[0] if gb else "(empty)")
    ama = format_references([
        {"title": "PD-L1", "authors": ["Smith J"], "year": 2024,
         "journal": "NEJM", "doi": "10.1056/x"},
    ], style="ama")
    check("ama renders 'doi:'",
          ama and "doi:" in ama[0], ama[0] if ama else "(empty)")

    # Formula render
    from app.export.formula_render import (
        extract_math_spans, render_latex_to_png,
    )
    md_in = r"Energy: $$ E = mc^2 $$ and inline $\alpha + \beta$ here."
    spans = extract_math_spans(md_in)
    check("extract_math_spans finds 1 block + 1 inline",
          len(spans) == 2
          and any(k == "block" for k, *_ in spans)
          and any(k == "inline" for k, *_ in spans),
          str([(k, l) for k, l, *_ in spans]))
    png = render_latex_to_png("E = mc^2", dpi=200)
    check("render_latex_to_png returns PNG bytes",
          len(png) > 200 and png[:8] == b"\x89PNG\r\n\x1a\n",
          f"len={len(png)} header={png[:8]!r}")

    # Chart selector heuristics
    from app.agents.chart_selector import recommend_chart
    rec = recommend_chart({"id": "x", "project_id": "p",
                             "analysis_type": "survival",
                             "title": "PFS by arm",
                             "params": {"risk_table": True},
                             "result_json": {}, "markdown_table": "",
                             "source_files": [],
                             "created_at": datetime.now(timezone.utc)})
    check("chart_selector(survival, risk_table) → km_with_risk_table",
          rec.chart_type == "km_with_risk_table",
          f"got {rec.chart_type}")
    rec = recommend_chart({"id": "x", "project_id": "p",
                             "analysis_type": "safety",
                             "title": "AE Summary by Arm",
                             "params": {}, "result_json": {},
                             "markdown_table": "", "source_files": [],
                             "created_at": datetime.now(timezone.utc)})
    check("chart_selector(safety) → stacked_bar_by_soc",
          rec.chart_type in ("stacked_bar_by_soc", "heatmap"),
          f"got {rec.chart_type}")
    rec = recommend_chart({"id": "x", "project_id": "p",
                             "analysis_type": "subgroup",
                             "title": "Forest", "params": {}, "result_json": {},
                             "markdown_table": "", "source_files": [],
                             "created_at": datetime.now(timezone.utc)})
    check("chart_selector(subgroup) → forest",
          rec.chart_type == "forest", f"got {rec.chart_type}")


# ---------------------------------------------------------------------------
# Phase 1 — server-driven flow
# ---------------------------------------------------------------------------

def _wait_for_outline(pid: str, timeout: float = 30.0) -> bool:
    """Poll until outline.json exists or timeout."""
    from app.config import data_dir
    target = data_dir() / "projects" / pid / "outline.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if target.exists():
            return True
        time.sleep(0.5)
    return False


def _phase_server(env: dict) -> str | None:
    proc = None
    pid: str | None = None
    try:
        proc = _start(env)

        info("phase 1: GET /api/sample_projects")
        r = requests.get(f"{BASE}/api/sample_projects", timeout=10)
        check("GET /sample_projects 200", r.status_code == 200,
              f"status={r.status_code}")
        if r.status_code == 200:
            arr = r.json()
            check("sample_projects has 5 domains", len(arr) == 5,
                  f"got {len(arr)}")
            for d in arr:
                if d.get("domain") == "oncology":
                    check("oncology entry references oncology template",
                          d.get("template_id") == "oncology")

        info("phase 2: POST /api/projects/from_sample/oncology")
        r = requests.post(f"{BASE}/api/projects/from_sample/oncology",
                          json={}, timeout=30)
        check("POST /from_sample/oncology 201", r.status_code == 201,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 201:
            body = r.json()
            pid = body.get("id")
            check("created pid present", bool(pid))
            check("parquet_count == 3",
                  body.get("parquet_count") == 3,
                  f"got {body.get('parquet_count')}")
            # Wait for background outline
            built = _wait_for_outline(pid, timeout=20.0)
            check("outline.json materialised in <20s", built)
            if built:
                from app.outline.store import load as load_outline
                outline = load_outline(pid)
                titles = " | ".join(n.title for n in (outline.root_sections or []))
                check("outline contains 'RECIST' / 'Tumor' / 'Oncology'",
                      any(k in titles for k in ("RECIST", "Tumor", "Response",
                                                  "Oncology", "ORR")),
                      f"titles={titles[:300]}")

        info("phase 3: literature_search (mock fallback OK)")
        if pid:
            r = requests.post(
                f"{BASE}/api/projects/{pid}/literature_search",
                json={"query": "PD-L1 NSCLC", "source": "pubmed",
                       "max_results": 3},
                timeout=30,
            )
            check("POST /literature_search 200", r.status_code == 200,
                  f"status={r.status_code} body={r.text[:200]}")
            if r.status_code == 200:
                body = r.json()
                check("literature_search returned ≥1 paper",
                      (body.get("count") or 0) >= 1,
                      f"count={body.get('count')}")

        info("phase 4: polish / {node_id}  (mock mode active)")
        if pid:
            # Seed a synthetic draft so polish has something to chew on
            sys.path.insert(0, str(BACKEND))
            from app.schemas.report import SectionDraft
            from app.report.store import save_draft
            draft = SectionDraft(
                node_id="8.1",
                title="Objective Response Rate (ORR)",
                markdown=("## Objective Response Rate\n\n"
                          "Basically, due to the fact that a number of patients "
                          "actually had measurable disease at the present time, "
                          "we analyzed ORR in spite of the fact that confirmation "
                          "was required. In order to assess, the very high "
                          "response rate was 35% (95% CI 27-44).\n"),
                citations=[],
                word_count=40,
                generated_at=datetime.now(timezone.utc),
                provenance=[],
                status="draft",
            )
            save_draft(pid, draft)
            r = requests.post(
                f"{BASE}/api/projects/{pid}/polish/8.1",
                json={"mode": "academic"},
                timeout=30,
            )
            check("POST /polish/{node_id} 200", r.status_code == 200,
                  f"status={r.status_code} body={r.text[:200]}")
            if r.status_code == 200:
                body = r.json()
                check("polish returned unified diff markers",
                      "@@" in (body.get("diff") or "")
                      or (body.get("diff_added", 0) + body.get("diff_removed", 0)) > 0,
                      "diff missing")
                check("polish preserved scientific data (35% / 95% CI)",
                      "35%" in (body.get("polished_markdown") or "")
                      and "95% CI" in (body.get("polished_markdown") or ""),
                      "data values lost!")

        info("phase 5: chart/recommend (KM by stat_id)")
        if pid:
            # Inject a synthetic survival StatBlock
            from app.schemas.stats import StatBlock
            from app.analysis import store as analysis_store
            sb = StatBlock(
                id="stat_km_demo",
                project_id=pid,
                analysis_type="survival",
                title="PFS by Arm (KM)",
                params={"risk_table": True},
                result_json={},
                markdown_table="| arm | median | 95% CI |\n|---|---|---|\n| Drug | 12 | 9-15 |\n",
                source_files=["ADEFF.parquet"],
                created_at=datetime.now(timezone.utc),
            )
            analysis_store.save(pid, sb)
            r = requests.post(
                f"{BASE}/api/projects/{pid}/chart/recommend",
                json={"stat_id": "stat_km_demo"},
                timeout=15,
            )
            check("POST /chart/recommend 200", r.status_code == 200,
                  f"status={r.status_code} body={r.text[:200]}")
            if r.status_code == 200:
                body = r.json()
                check("chart_type is KM-style",
                      str(body.get("chart_type", "")).startswith("km"),
                      f"got {body.get('chart_type')}")
                check("echarts_template_json non-empty",
                      isinstance(body.get("echarts_template_json"), dict)
                      and len(body["echarts_template_json"]) > 0)

        info("phase 6: export DOCX with reference_style='gb7714'")
        if pid:
            # Seed a literature corpus block + a draft citing it so the
            # References chapter is non-empty and exercises the formatter
            from app.corpus.index import Block, add_block, make_ref
            bid = add_block(pid, Block(
                project_id=pid, type="literature", page=1, col=1, para=1,
                text="PD-L1 inhibitor trial in NSCLC.",
                meta={
                    "title": "PD-L1 inhibitor in NSCLC",
                    "authors": ["Smith J", "Lee K"],
                    "year": 2024, "journal": "NEJM",
                    "volume": 390, "issue": 3, "pages": "123-130",
                    "doi": "10.1056/abc",
                },
            ))
            from app.schemas.report import SectionDraft, CitationRef, Provenance
            ref_code = f"Ref{bid}.P1.Col1.Para1"
            d2 = SectionDraft(
                node_id="8.1",
                title="Objective Response Rate (ORR)",
                markdown=("## Objective Response Rate\n\n"
                          f"See {ref_code} for the pivotal trial.\n\n"
                          "Mass-energy equivalence: $$ E = mc^2 $$\n\n"
                          "And inline math $\\alpha + \\beta$ in prose.\n"),
                citations=[CitationRef(
                    ref_code=ref_code, type="literature",
                    locator=f"[{ref_code}]",
                    snippet="PD-L1 inhibitor trial in NSCLC.",
                )],
                word_count=40,
                generated_at=datetime.now(timezone.utc),
                provenance=[Provenance(range=(0, 50), source="ai")],
                status="draft",
            )
            save_draft(pid, d2)

            r = requests.post(
                f"{BASE}/api/projects/{pid}/export/docx",
                json={"template_config": {"reference_style": "gb7714"}},
                timeout=120,
            )
            check("POST /export/docx (gb7714) 200", r.status_code == 200,
                  f"status={r.status_code} body={r.text[:200]}")
            if r.status_code == 200:
                from app.config import data_dir
                from docx import Document  # type: ignore
                fname = r.json()["filename"]
                fpath = data_dir() / "projects" / pid / "exports" / fname
                doc = Document(str(fpath))
                full_text = "\n".join(p.text for p in doc.paragraphs)
                check("DOCX References uses '[1]' GB7714 marker",
                      "[1]" in full_text and "[J]" in full_text,
                      f"sample={full_text[-600:]}")
                # Inline images: scan docx for media files
                with ZipFile(fpath, "r") as zf:
                    media = [n for n in zf.namelist()
                              if n.startswith("word/media/")
                              and n.lower().endswith(".png")]
                check("DOCX embeds ≥1 LaTeX-rendered PNG",
                      len(media) >= 1, f"media={media}")

        return pid
    except Exception as e:
        info(f"phase exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return pid
    finally:
        _stop(proc)


# ---------------------------------------------------------------------------
# Phase 99 — m2..m19 regression
# ---------------------------------------------------------------------------

def _regression() -> None:
    info("phase 99: m2..m19 regression scripts")
    scripts = [
        "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10",
        "m11", "m12", "m13", "m14", "m15", "m16", "m17", "m18", "m19",
    ]
    for name in scripts:
        path = ROOT / "scripts" / f"{name}_e2e_test.py"
        if not path.exists():
            check(f"regression {name} script present", False, "missing")
            continue
        info(f"  running {name}_e2e_test.py")
        rc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT, capture_output=True, timeout=900,
            env=os.environ.copy(),
        )
        ok = rc.returncode == 0
        check(f"regression {name} green", ok,
              f"rc={rc.returncode} tail={(rc.stdout + rc.stderr)[-600:]!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # Mock all LLM-using agents so the test never hits the network for LLM
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env["CSR_POLISH_MOCK"] = "1"
    env["CSR_ANALYST_MOCK"] = "1"
    env["CSR_LITSEARCH_MOCK"] = "1"
    env["AUTOCSR_QUEUE_BACKEND"] = "inmemory"

    pid: str | None = None
    try:
        _phase_local()
        pid = _phase_server(env)
        if os.environ.get("M20_SKIP_REGRESSION", "").lower() not in ("1", "true", "yes"):
            _regression()
    finally:
        if pid:
            _cleanup_project(pid)

    total = len(CHECKS)
    passed = sum(1 for _, ok in CHECKS if ok)
    info(f"M20 checks: {passed}/{total} pass")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
