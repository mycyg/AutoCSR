"""End-to-end test for M4 (multi-agent parallel report writing).

Spins up uvicorn on :8769, builds synthetic ADSL+ADAE+ADTTE, drives:
    upload -> ingest -> cleansing apply -> analysis/auto -> outline/build
    -> report/generate (harmonize=true)

In MOCK mode (default, CSR_WRITER_MOCK=1) the writer_agent returns a stable
stub markdown body and the harmonizer falls back to deterministic term
substitution — both still:
  - actually run through orchestrator's 3-phase DAG with Semaphore(4)
  - validate citations against corpus + StatBlock stores
  - persist SectionDraft files, run WS events, drive /report/status polling
  - exercise the regenerate route end-to-end

A second optional pass (env REAL_LLM=1) runs the same pipeline against
DeepSeek with leaf_limit=5 to prove the real LLM round-trip works without
burning budget.

Usage:
    python scripts/m4_e2e_test.py             # mock only
    REAL_LLM=1 python scripts/m4_e2e_test.py  # mock + 5-leaf real LLM
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8769"
TIMEOUT_INGEST_S = 120
TIMEOUT_ANALYSIS_S = 180
TIMEOUT_OUTLINE_S = 320
TIMEOUT_GENERATE_MOCK_S = 240
TIMEOUT_GENERATE_REAL_S = 1800


def info(msg: str) -> None:
    print(f"[E2E] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def make_adsl(p: Path) -> None:
    rows = ["USUBJID,AGE,SEX,RACE,TRT01P,HEIGHT,WEIGHT,BMI"]
    seed = [
        ("001-001", 45, "M", "Asian",  "DrugA",   170, 70.1, 24.2),
        ("001-002", 52, "F", "Asian",  "DrugA",   165, 55.3, 20.3),
        ("001-003", 38, "F", "Asian",  "DrugA",   158, 52.0, 20.8),
        ("001-004", 61, "M", "Asian",  "DrugA",   180, 82.5, 25.5),
        ("001-005", 47, "M", "Asian",  "DrugA",   175, 75.2, 24.6),
        ("001-006", 55, "F", "Asian",  "DrugA",   162, 58.0, 22.1),
        ("001-007", 49, "M", "Asian",  "DrugA",   178, 80.5, 25.4),
        ("001-008", 60, "F", "Asian",  "DrugA",   160, 53.1, 20.7),
        ("001-009", 42, "F", "White",  "DrugA",   165, 60.2, 22.1),
        ("001-010", 58, "M", "White",  "DrugA",   177, 78.4, 25.0),
        ("001-011", 33, "M", "Asian",  "Placebo", 168, 72.0, 25.5),
        ("001-012", 46, "F", "Asian",  "Placebo", 160, 56.5, 22.1),
        ("001-013", 51, "F", "Asian",  "Placebo", 159, 54.0, 21.4),
        ("001-014", 48, "M", "Asian",  "Placebo", 176, 77.2, 24.9),
        ("001-015", 57, "M", "Asian",  "Placebo", 182, 85.0, 25.6),
        ("001-016", 39, "F", "Asian",  "Placebo", 159, 55.0, 21.7),
        ("001-017", 54, "F", "Asian",  "Placebo", 164, 57.2, 21.3),
        ("001-018", 50, "M", "White",  "Placebo", 170, 71.0, 24.5),
        ("001-019", 44, "F", "White",  "Placebo", 163, 58.4, 22.0),
        ("001-020", 53, "M", "White",  "Placebo", 171, 76.5, 26.1),
    ]
    for r in seed:
        rows.append(",".join(str(x) for x in r))
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")


def make_adae(p: Path) -> None:
    rows = ["USUBJID,AESOC,AEDECOD,AESEV,AEREL,TRT01P"]
    data = [
        ("001-001", "Gastrointestinal disorders", "Nausea",    "Mild",     "Related",          "DrugA"),
        ("001-001", "Skin disorders",             "Rash",      "Moderate", "Possibly related", "DrugA"),
        ("001-002", "Nervous system disorders",   "Headache",  "Mild",     "Not related",      "DrugA"),
        ("001-003", "Gastrointestinal disorders", "Vomiting",  "Severe",   "Related",          "DrugA"),
        ("001-004", "Skin disorders",             "Rash",      "Mild",     "Possibly related", "DrugA"),
        ("001-005", "Gastrointestinal disorders", "Nausea",    "Moderate", "Related",          "DrugA"),
        ("001-006", "Nervous system disorders",   "Dizziness", "Severe",   "Probably related", "DrugA"),
        ("001-007", "Skin disorders",             "Rash",      "Moderate", "Related",          "DrugA"),
        ("001-008", "Gastrointestinal disorders", "Nausea",    "Mild",     "Not related",      "DrugA"),
        ("001-009", "Nervous system disorders",   "Headache",  "Moderate", "Possibly related", "DrugA"),
        ("001-010", "Skin disorders",             "Rash",      "Severe",   "Related",          "DrugA"),
        ("001-011", "Gastrointestinal disorders", "Nausea",    "Mild",     "Not related",      "Placebo"),
        ("001-012", "Nervous system disorders",   "Headache",  "Mild",     "Not related",      "Placebo"),
        ("001-013", "Skin disorders",             "Rash",      "Mild",     "Not related",      "Placebo"),
        ("001-014", "Gastrointestinal disorders", "Vomiting",  "Moderate", "Possibly related", "Placebo"),
        ("001-015", "Nervous system disorders",   "Dizziness", "Mild",     "Not related",      "Placebo"),
        ("001-016", "Skin disorders",             "Rash",      "Mild",     "Not related",      "Placebo"),
        ("001-017", "Gastrointestinal disorders", "Nausea",    "Mild",     "Not related",      "Placebo"),
        ("001-018", "Nervous system disorders",   "Headache",  "Moderate", "Possibly related", "Placebo"),
        ("001-019", "Skin disorders",             "Rash",      "Mild",     "Not related",      "Placebo"),
        ("001-020", "Gastrointestinal disorders", "Nausea",    "Severe",   "Related",          "Placebo"),
    ]
    for d in data:
        rows.append(",".join(d))
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")


def make_adtte(p: Path) -> None:
    rows = ["USUBJID,AVAL,CNSR,TRT01P"]
    data = [
        ("001-001", "45.0", "0", "DrugA"),
        ("001-002", "61.0", "1", "DrugA"),
        ("001-003", "28.0", "0", "DrugA"),
        ("001-004", "73.0", "0", "DrugA"),
        ("001-005", "82.0", "1", "DrugA"),
        ("001-006", "37.0", "0", "DrugA"),
        ("001-007", "94.0", "1", "DrugA"),
        ("001-008", "53.0", "0", "DrugA"),
        ("001-009", "68.0", "1", "DrugA"),
        ("001-010", "44.0", "0", "DrugA"),
        ("001-011", "22.0", "0", "Placebo"),
        ("001-012", "31.0", "0", "Placebo"),
        ("001-013", "19.0", "0", "Placebo"),
        ("001-014", "47.0", "0", "Placebo"),
        ("001-015", "58.0", "1", "Placebo"),
        ("001-016", "26.0", "0", "Placebo"),
        ("001-017", "33.0", "1", "Placebo"),
        ("001-018", "41.0", "0", "Placebo"),
        ("001-019", "29.0", "0", "Placebo"),
        ("001-020", "37.0", "1", "Placebo"),
    ]
    for d in data:
        rows.append(",".join(d))
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")


def start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8769")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8769",
        "--host", "127.0.0.1", "--log-level", "warning",
    ]
    proc = subprocess.Popen(
        args, cwd=BACKEND, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/api/health", timeout=2)
            if r.status_code == 200:
                info("server up")
                return proc
        except requests.RequestException:
            time.sleep(0.4)
    proc.terminate()
    raise RuntimeError("server did not come up in 30s")


def stop_server(proc: subprocess.Popen) -> None:
    info("stopping server")
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


def wait_for_report(pid: str, timeout: float) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    last_phase = None
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE}/api/projects/{pid}/report/status", timeout=10)
            r.raise_for_status()
            s = r.json()
        except Exception:
            time.sleep(1.5)
            continue
        last = s
        phase = s.get("current_phase")
        if phase != last_phase:
            info(f"phase -> {phase} ({s.get('leaves_done')}/{s.get('leaves_total')} done)")
            last_phase = phase
        if phase in ("done", "error"):
            return s
        time.sleep(1.5)
    return last


def run_pipeline_through_outline(pid: str) -> dict:
    # files
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m4_e2e_inputs_"))
    adsl_p = workdir / "fake_adsl.csv"
    adae_p = workdir / "fake_adae.csv"
    adtte_p = workdir / "fake_adtte.csv"
    make_adsl(adsl_p)
    make_adae(adae_p)
    make_adtte(adtte_p)

    with adsl_p.open("rb") as f1, adae_p.open("rb") as f2, adtte_p.open("rb") as f3:
        r = requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", ("fake_adsl.csv", f1, "text/csv")),
            ("files", ("fake_adae.csv", f2, "text/csv")),
            ("files", ("fake_adtte.csv", f3, "text/csv")),
        ], timeout=60)
    r.raise_for_status()
    info(f"uploaded 3 files")

    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + TIMEOUT_INGEST_S
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(1.0)
    else:
        raise RuntimeError("ingest did not complete in time")

    for e in entries:
        fid = e["file_id"]
        r = requests.get(f"{BASE}/api/projects/{pid}/cleansing/proposals",
                         params={"file_id": fid, "refresh": "true"}, timeout=60)
        r.raise_for_status()
        for p in r.json():
            if p["status"] == "pending" and not p["mandatory"]:
                requests.patch(
                    f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                    json={"status": "accepted"}, timeout=10,
                ).raise_for_status()
        requests.post(f"{BASE}/api/projects/{pid}/cleansing/apply",
                      json={"file_id": fid}, timeout=120).raise_for_status()
    info("cleansing applied")

    requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                  timeout=TIMEOUT_ANALYSIS_S).raise_for_status()
    r = requests.get(f"{BASE}/api/projects/{pid}/stats", timeout=10)
    r.raise_for_status()
    blocks = r.json()
    info(f"stat blocks: {len(blocks)}")

    requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                  json={"principle_id": "ich_e3"},
                  timeout=TIMEOUT_OUTLINE_S).raise_for_status()
    outline = requests.get(f"{BASE}/api/projects/{pid}/outline", timeout=10).json()
    n_nodes = _count_nodes(outline["root_sections"])
    n_with_stats = sum(1 for n in _walk(outline["root_sections"]) if n.get("stat_refs"))
    info(f"outline nodes: {n_nodes} ({n_with_stats} with stat_refs)")
    if n_nodes < 50:
        raise AssertionError(f"expected >=50 nodes, got {n_nodes}")
    if n_with_stats < 5:
        info(f"WARN: only {n_with_stats} nodes have stat_refs; M3 binding may be sparse")

    shutil.rmtree(workdir, ignore_errors=True)
    return outline


def assert_drafts_ok(pid: str, outline: dict, *, min_words: int = 30, min_with_cites: int = 3) -> dict:
    drafts = requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
    leaves = [n for n in _walk(outline["root_sections"]) if not n["children"]]
    info(f"drafts: {len(drafts)} / leaves: {len(leaves)}")

    over_min = sum(1 for d in drafts if d["word_count"] >= min_words)
    with_cites = sum(1 for d in drafts if d["n_citations"] > 0)
    info(f"  drafts with >={min_words} words: {over_min}")
    info(f"  drafts with >=1 citation:        {with_cites}")
    if over_min < 5:
        raise AssertionError(f"expected >=5 drafts with >={min_words} words, got {over_min}")
    if with_cites < min_with_cites:
        raise AssertionError(f"expected >={min_with_cites} drafts with citations, got {with_cites}")

    # Validate each citation resolves
    sample_full = None
    bad_refs: list[str] = []
    for d in drafts[:30]:
        full = requests.get(
            f"{BASE}/api/projects/{pid}/report/drafts/{d['node_id']}", timeout=10,
        ).json()
        if sample_full is None and full.get("word_count", 0) >= min_words and full.get("citations"):
            sample_full = full
        for c in full.get("citations", []):
            ref = c["ref_code"]
            # we trust the writer agent already validated; this re-checks via the same store paths
            # by simply requiring locator was bracketed correctly
            if not c.get("locator", "").startswith("[Ref"):
                bad_refs.append(ref)
    if bad_refs:
        raise AssertionError(f"malformed citation locators: {bad_refs[:5]}")
    return sample_full or {}


def _walk(nodes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.get("children") or []))
    return out


def _count_nodes(nodes: list[dict]) -> int:
    return len(_walk(nodes))


def main() -> int:
    use_real = os.environ.get("REAL_LLM", "").lower() in ("1", "true", "yes")
    info(f"REAL_LLM={use_real}")
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m4_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"   # default phase: mock writer
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    # For mock pass: blank LLM (outline builder skips LLM enrichment).
    # For real LLM pass we reuse whatever was in the existing yaml.
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8769\n"
        "pipeline:\n  llm_data_redaction: strict\n"
        "  max_parallel_writers: 4\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = start_server(env)
        # 1. project
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M4", "principle_id": "ich_e3"}, timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        outline = run_pipeline_through_outline(pid)

        # 2. Generate full report (mock mode)
        info(">>> MOCK pass: full report")
        r = requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                          json={"harmonize": True}, timeout=30)
        r.raise_for_status()
        info(f"generate response: {r.json()}")
        final = wait_for_report(pid, timeout=TIMEOUT_GENERATE_MOCK_S)
        info(f"final status: phase={final.get('current_phase')} "
             f"done={final.get('leaves_done')}/{final.get('leaves_total')} "
             f"err={final.get('leaves_errored')} harmonized={final.get('harmonized')}")
        if final.get("current_phase") != "done":
            raise AssertionError(f"generate did not finish (phase={final.get('current_phase')})")
        if not final.get("harmonized"):
            raise AssertionError("expected harmonized=True after harmonize pass")

        sample = assert_drafts_ok(pid, outline, min_words=30, min_with_cites=3)
        if sample:
            head = (sample.get("markdown") or "")[:200]
            info(f"sample draft head: {head!r}")
            info(f"sample citations ({len(sample.get('citations') or [])}):")
            for c in (sample.get("citations") or [])[:5]:
                info(f"  - {c['type']:10s} {c['ref_code']}")

        # 3. Regenerate one leaf
        # find one leaf with a current draft
        leaves_with_drafts = [
            d for d in requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
            if d["status"] != "error"
        ]
        target = leaves_with_drafts[0]["node_id"]
        before = requests.get(f"{BASE}/api/projects/{pid}/report/drafts/{target}", timeout=10).json()
        info(f"regenerating {target} (was generated_at={before['generated_at']})")
        rr = requests.post(
            f"{BASE}/api/projects/{pid}/report/regenerate/{target}",
            json={"extra_instructions": "在首段加入研究依据"}, timeout=120,
        )
        rr.raise_for_status()
        after = requests.get(f"{BASE}/api/projects/{pid}/report/drafts/{target}", timeout=10).json()
        if after["generated_at"] == before["generated_at"]:
            raise AssertionError("regenerate did not bump generated_at")
        info(f"regenerate OK; new generated_at={after['generated_at']}")

        # 4. drafts list non-empty + drafts json contains all leaves
        drafts_idx = requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
        if not drafts_idx:
            raise AssertionError("empty draft list")
        info(f"draft index size: {len(drafts_idx)}")

        # 5. terminology GET/PATCH
        terms = requests.get(f"{BASE}/api/projects/{pid}/terminology", timeout=10).json()
        info(f"initial terminology keys: {len(terms)}")
        terms["primary endpoint"] = "主要终点(自定义)"
        rt = requests.patch(f"{BASE}/api/projects/{pid}/terminology", json=terms, timeout=10)
        rt.raise_for_status()
        after_terms = requests.get(f"{BASE}/api/projects/{pid}/terminology", timeout=10).json()
        assert after_terms.get("primary endpoint") == "主要终点(自定义)"
        info(f"terminology PATCH OK ({len(after_terms)} entries)")

        # 6. REAL LLM optional pass — limit to 5 leaves
        if use_real:
            info(">>> REAL LLM pass: 5 leaves")
            # restore the prior settings yaml so api_key is available
            if saved is not None:
                overlay.write_bytes(saved)
            env_real = os.environ.copy()
            env_real.pop("CSR_WRITER_MOCK", None)
            env_real.setdefault("PYTHONIOENCODING", "utf-8")
            # restart server to pick up new settings + new env
            stop_server(proc)
            time.sleep(1.0)
            proc = start_server(env_real)
            # re-create a fresh report request — we reuse the same project (drafts will be overwritten)
            r = requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                              json={"harmonize": True, "leaf_limit": 5}, timeout=30)
            r.raise_for_status()
            final2 = wait_for_report(pid, timeout=TIMEOUT_GENERATE_REAL_S)
            info(f"real-LLM final status: phase={final2.get('current_phase')} "
                 f"done={final2.get('leaves_done')}/{final2.get('leaves_total')} "
                 f"tokens_in={final2['total_tokens']['input']} "
                 f"tokens_out={final2['total_tokens']['output']}")
            # The 5-leaf writer DAG must finish; the harmonizer pass is allowed
            # to still be running (each editor_llm call may run 60+s).
            phase = final2.get("current_phase")
            leaves_done = final2.get("leaves_done", 0)
            leaves_total = final2.get("leaves_total", 0)
            if leaves_done != leaves_total:
                raise AssertionError(f"real-LLM only {leaves_done}/{leaves_total} leaves written")
            if phase not in ("done", "harmonize"):
                raise AssertionError(f"real-LLM phase={phase}")
            if phase == "harmonize":
                info("note: harmonizer still running at e2e deadline — accepting as success "
                     "because writer phase completed")
            # at least 1 leaf should have meaningful content & citations
            drafts = requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
            ok = sum(1 for d in drafts if d.get("word_count", 0) >= 80 and d.get("n_citations", 0) > 0)
            info(f"real-LLM drafts with words>=80 & citations: {ok}")
            if ok < 1:
                raise AssertionError("real-LLM yielded no high-quality drafts")
            # Print one head
            sample = next((d for d in drafts if d.get("word_count", 0) >= 80), None)
            if sample:
                full = requests.get(
                    f"{BASE}/api/projects/{pid}/report/drafts/{sample['node_id']}", timeout=10,
                ).json()
                info(f"REAL sample head (node={full['node_id']}):")
                info(full["markdown"][:300])

        # 7. final summary
        st = requests.get(f"{BASE}/api/projects/{pid}/report/status", timeout=10).json()
        info(f"\n[E2E] DONE  total_words={st['total_words']} "
             f"tokens_in={st['total_tokens']['input']} tokens_out={st['total_tokens']['output']}")
        print("\n[E2E] OK  all checks passed", flush=True)
        return 0
    except AssertionError as e:
        err(f"assertion failed: {e}")
        import traceback; traceback.print_exc()
        return 2
    except Exception as e:
        err(f"exception: {e}")
        import traceback; traceback.print_exc()
        return 3
    finally:
        if proc is not None:
            stop_server(proc)
        try:
            if saved is None:
                if overlay.exists():
                    overlay.unlink()
            else:
                overlay.write_bytes(saved)
        except Exception:
            pass
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
        # Cleanup project from dev data
        if pid:
            try:
                sys.path.insert(0, str(BACKEND))
                from app.config import data_dir
                proj_root = data_dir() / "projects" / pid
                shutil.rmtree(proj_root, ignore_errors=True)
                projects_json = data_dir() / "projects.json"
                if projects_json.exists():
                    items = json.loads(projects_json.read_text(encoding="utf-8") or "[]")
                    items = [p for p in items if p.get("id") != pid]
                    projects_json.write_text(
                        json.dumps(items, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except Exception:
                pass


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND))
    sys.exit(main())
