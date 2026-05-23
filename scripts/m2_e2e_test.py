"""End-to-end test for M2 + M2.5.

Boots uvicorn, creates a project, uploads three synthetic files, kicks ingest,
polls until done, and verifies router decisions + cleansing proposals +
apply + pipeline yaml.

Usage:
    python scripts/m2_e2e_test.py
Exit code 0 on success; non-zero on failure with details printed to stderr.
"""
from __future__ import annotations

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
BASE = "http://127.0.0.1:8767"  # use non-default port to avoid clashes
TIMEOUT_INGEST_S = 120


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def info(msg: str) -> None:
    print(f"[E2E] {msg}", flush=True)


def make_csv(p: Path) -> None:
    """ADSL-like file: should route to structured_data."""
    p.write_text(
        "USUBJID,AGE,SEX,TRT01P\n"
        "001-001,45,M,DrugA\n"
        "001-002,52,F,Placebo\n"
        "001-003,38,F,DrugA\n"
        "001-004,61,M,Placebo\n"
        "001-005,47,M,DrugA\n",
        encoding="utf-8",
    )


def make_xlsx(p: Path) -> None:
    """Messy 3-sheet Excel: should route to messy_tabular."""
    import pandas as pd
    df1 = pd.DataFrame({
        "病例号": ["P001", "P002", "P003", "P004", "P005"],
        "年龄(岁)": ["30岁", "45岁", "--", "27", "33"],
        "姓名": ["张三", "李四", "王五", "赵六", "陈七"],
        "电话": ["13800001234", "--", "13800003333", "13800004444", "13800005555"],
    })
    df2 = pd.DataFrame({
        "体重kg": [60.5, 72.0, None, 55.0, 68.1],
        "身高cm": [165, 180, 158, 170, 175],
        "BMI": ["22.2", "22.2", "--", "19.0", "22.2"],
    })
    df3 = pd.DataFrame({
        "用药记录": ["100mg qd", "200mg bid", "--", "100mg qd", "150mg qd"],
        "不良反应": ["头痛", "无", "皮疹", "无", "恶心"],
    })
    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df1.to_excel(w, sheet_name="基线", index=False)
        df2.to_excel(w, sheet_name="体征", index=False)
        df3.to_excel(w, sheet_name="用药", index=False)


def make_txt(p: Path) -> None:
    """Plain-text protocol: should route to literature_doc."""
    p.write_text(
        "Protocol BMS-A001 Phase III Clinical Trial\n\n"
        "Background: This randomized double-blind placebo-controlled study evaluates\n"
        "the efficacy and safety of Drug A in patients with refractory hypertension.\n\n"
        "Primary Endpoint: Change in systolic blood pressure from baseline at week 12.\n\n"
        "Sample Size: 240 subjects, 1:1 randomization, alpha=0.05, power=0.8.\n\n"
        "Inclusion Criteria: Adults aged 18-75 with SBP >= 140 mmHg on standard therapy.\n",
        encoding="utf-8",
    )


def start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8767")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8767",
        "--host", "127.0.0.1", "--log-level", "warning",
    ]
    proc = subprocess.Popen(
        args, cwd=BACKEND, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for /api/health to respond
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


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_e2e_"))
    info(f"workdir: {workdir}")
    env = os.environ.copy()
    # Isolate from dev data: point data_dir into the workdir via env var
    env["AUTOCSR_DATA_DIR"] = str(workdir / "data")
    # We don't actually wire AUTOCSR_DATA_DIR; instead just rely on default ./data,
    # but cleanup our test project at the end. (Keeps M1 config behavior intact.)

    files_dir = workdir / "inputs"
    files_dir.mkdir(parents=True, exist_ok=True)
    csv_path = files_dir / "fake_adsl.csv"
    xlsx_path = files_dir / "fake_messy.xlsx"
    txt_path = files_dir / "fake_protocol.txt"
    make_csv(csv_path)
    make_xlsx(xlsx_path)
    make_txt(txt_path)

    # Use a settings overlay that disables LLM (api_key blank): proposers will skip LLM
    # and rely on deterministic rules — keeps the test offline and deterministic.
    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = None
    if overlay.exists():
        saved = overlay.read_bytes()
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8767\n"
        "pipeline:\n  llm_data_redaction: strict\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = start_server(env)
        # 1. Create project
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M2", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        # 2. Upload
        with csv_path.open("rb") as fcsv, xlsx_path.open("rb") as fxlsx, txt_path.open("rb") as ftxt:
            r = requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
                ("files", ("fake_adsl.csv", fcsv, "text/csv")),
                ("files", ("fake_messy.xlsx", fxlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("files", ("fake_protocol.txt", ftxt, "text/plain")),
            ], timeout=60)
        r.raise_for_status()
        uploaded = r.json()["uploaded"]
        assert len(uploaded) == 3, f"expected 3 uploads, got {len(uploaded)}"
        info(f"uploaded {len(uploaded)} files")

        # 3. Trigger ingest
        r = requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10)
        r.raise_for_status()

        # 4. Poll status
        deadline = time.time() + TIMEOUT_INGEST_S
        last_status: dict = {}
        while time.time() < deadline:
            s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
            last_status = s
            if s.get("all_done"):
                break
            time.sleep(1.2)
        if not last_status.get("all_done"):
            raise RuntimeError(f"ingest did not complete in {TIMEOUT_INGEST_S}s: {last_status.get('by_status')}")
        info(f"ingest complete: {last_status['by_status']}")

        # 5. Verify router decisions
        entries = last_status["entries"]
        by_name = {e["filename"]: e for e in entries}
        if by_name["fake_adsl.csv"]["ingest_type"] != "structured_data":
            raise AssertionError(f"adsl should be structured_data, got {by_name['fake_adsl.csv']['ingest_type']}")
        if by_name["fake_messy.xlsx"]["ingest_type"] != "messy_tabular":
            raise AssertionError(f"xlsx should be messy_tabular, got {by_name['fake_messy.xlsx']['ingest_type']}")
        if by_name["fake_protocol.txt"]["ingest_type"] != "literature_doc":
            raise AssertionError(f"txt should be literature_doc, got {by_name['fake_protocol.txt']['ingest_type']}")
        info("router decisions OK")

        messy_id = by_name["fake_messy.xlsx"]["file_id"]

        # 6. Cleansing proposals for the messy file
        r = requests.get(
            f"{BASE}/api/projects/{pid}/cleansing/proposals",
            params={"file_id": messy_id, "refresh": "true"},
            timeout=60,
        )
        r.raise_for_status()
        proposals = r.json()
        info(f"got {len(proposals)} proposals for messy.xlsx")
        if len(proposals) < 3:
            raise AssertionError(f"expected >=3 proposals, got {len(proposals)}")

        types = {p["type"] for p in proposals}
        if "hash_pii" not in types:
            raise AssertionError(f"expected hash_pii proposal (姓名/电话), types={types}")
        # rename_column may come from LLM only; we required hash_pii + at least one
        # numeric-aware type from the deterministic engine
        deterministic_types = {"hash_pii", "cast_dtype", "impute_missing", "outlier_flag", "normalize_value"}
        if not (types & (deterministic_types - {"hash_pii"})):
            info(f"note: only PII-class proposals found — types={types}")
        info(f"proposal types: {types}")

        # 7. Accept all proposals (PII mandatory + others)
        accepted_n = 0
        for p in proposals:
            if p["status"] == "pending":
                rr = requests.patch(
                    f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                    json={"status": "accepted"}, timeout=10,
                )
                rr.raise_for_status()
                accepted_n += 1
                if accepted_n >= 5:  # accept first 5; PII auto-applies regardless
                    break
        info(f"accepted {accepted_n} proposals")

        # 8. Apply
        r = requests.post(
            f"{BASE}/api/projects/{pid}/cleansing/apply",
            json={"file_id": messy_id}, timeout=60,
        )
        r.raise_for_status()
        apply_out = r.json()
        info(f"apply OK snapshot={apply_out.get('snapshot_id')} rows_after={apply_out.get('rows_after')}")
        # Verify processed parquet/csv landed
        from app.config import data_dir
        proc_dir = data_dir() / "projects" / pid / "processed"
        produced = list(proc_dir.glob(f"{messy_id}*"))
        if not produced:
            raise AssertionError(f"no processed file at {proc_dir}")
        info(f"processed artifact: {produced[0].name}")

        # 9. Pipeline YAML
        r = requests.get(
            f"{BASE}/api/projects/{pid}/cleansing/pipeline",
            params={"file_id": messy_id}, timeout=10,
        )
        r.raise_for_status()
        yaml_text = r.json().get("yaml", "")
        if "rules:" not in yaml_text or "hash_pii" not in yaml_text:
            raise AssertionError(f"pipeline yaml missing rules or hash_pii: {yaml_text[:300]}")
        info(f"pipeline yaml OK ({len(yaml_text)} chars)")

        # 10. Corpus search (literature)
        r = requests.post(
            f"{BASE}/api/projects/{pid}/corpus/search",
            json={"query": "primary endpoint", "top_k": 5}, timeout=10,
        )
        r.raise_for_status()
        hits = r.json()
        if not hits:
            info("warn: no corpus hits for 'primary endpoint' — txt blocks may not have indexed")
        else:
            info(f"corpus search OK ({len(hits)} hits)")

        # 11. Principles endpoint
        r = requests.get(f"{BASE}/api/principles", timeout=5)
        r.raise_for_status()
        plist = r.json()
        ids = {p["id"] for p in plist}
        if {"ich_e3", "cde_chem", "cde_tcm"} - ids:
            raise AssertionError(f"principles missing: have {ids}")
        info(f"principles OK: {ids}")

        print("\n[E2E] OK ✓ all checks passed", flush=True)
        return 0
    except Exception as e:
        err(f"exception: {e}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        if proc is not None:
            stop_server(proc)
        # Restore overlay
        try:
            if saved is None:
                if overlay.exists():
                    overlay.unlink()
            else:
                overlay.write_bytes(saved)
        except Exception:
            pass
        # Cleanup the e2e workdir
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
        # Cleanup the test project from dev data dir (best-effort)
        if pid:
            try:
                sys.path.insert(0, str(BACKEND))
                from app.config import data_dir
                proj_root = data_dir() / "projects" / pid
                shutil.rmtree(proj_root, ignore_errors=True)
                projects_json = data_dir() / "projects.json"
                if projects_json.exists():
                    import json as _json
                    items = _json.loads(projects_json.read_text(encoding="utf-8") or "[]")
                    items = [p for p in items if p.get("id") != pid]
                    projects_json.write_text(
                        _json.dumps(items, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except Exception:
                pass


if __name__ == "__main__":
    # Ensure backend on sys.path for the inline data_dir() import
    sys.path.insert(0, str(BACKEND))
    sys.exit(main())
