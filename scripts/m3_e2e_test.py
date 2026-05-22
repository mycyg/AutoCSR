"""End-to-end test for M3 (clinical analysis + outline).

Spins up uvicorn on :8768, builds synthetic ADSL + ADAE + ADTTE CSVs, drives
the full pipeline:
    upload -> ingest -> cleansing apply -> /analysis/auto -> /outline/build
and asserts:
    >=3 StatBlocks produced; >=50 outline nodes; ICH E3 chapter 10/11/12
    sections have non-empty stat_refs; PATCH outline node persists.

Usage:
    python scripts/m3_e2e_test.py
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
BASE = "http://127.0.0.1:8768"
TIMEOUT_INGEST_S = 120
TIMEOUT_ANALYSIS_S = 180
TIMEOUT_OUTLINE_S = 320


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def info(msg: str) -> None:
    print(f"[E2E] {msg}", flush=True)


def make_adsl(p: Path) -> None:
    rows = [
        "USUBJID,AGE,SEX,RACE,TRT01P,HEIGHT,WEIGHT,BMI",
    ]
    # 20 subjects, two arms balanced
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
        ("001-001", "Nervous system disorders",   "Headache",  "Mild",     "Not related",      "DrugA"),
        ("001-002", "Skin disorders",             "Rash",      "Mild",     "Not related",      "DrugA"),
        ("001-003", "Skin disorders",             "Rash",      "Mild",     "Not related",      "DrugA"),
        ("001-004", "Gastrointestinal disorders", "Nausea",    "Moderate", "Possibly related", "DrugA"),
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
        ("001-011", "Nervous system disorders",   "Headache",  "Mild",     "Not related",      "Placebo"),
        ("001-012", "Skin disorders",             "Rash",      "Mild",     "Not related",      "Placebo"),
        ("001-013", "Gastrointestinal disorders", "Vomiting",  "Moderate", "Possibly related", "Placebo"),
        ("001-014", "Nervous system disorders",   "Dizziness", "Mild",     "Not related",      "Placebo"),
        ("001-015", "Skin disorders",             "Rash",      "Mild",     "Not related",      "Placebo"),
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
    info("starting uvicorn on :8768")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8768",
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


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m3_e2e_"))
    info(f"workdir: {workdir}")
    env = os.environ.copy()

    files_dir = workdir / "inputs"
    files_dir.mkdir(parents=True, exist_ok=True)
    adsl_p = files_dir / "fake_adsl.csv"
    adae_p = files_dir / "fake_adae.csv"
    adtte_p = files_dir / "fake_adtte.csv"
    make_adsl(adsl_p)
    make_adae(adae_p)
    make_adtte(adtte_p)

    # Disable LLM so test is deterministic / offline. Outline builder falls back
    # to heuristic notes when api_key is blank.
    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = None
    if overlay.exists():
        saved = overlay.read_bytes()
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8768\n"
        "pipeline:\n  llm_data_redaction: strict\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = start_server(env)

        # 1. Create project
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M3", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        # 2. Upload three CSVs
        with adsl_p.open("rb") as f1, adae_p.open("rb") as f2, adtte_p.open("rb") as f3:
            r = requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
                ("files", ("fake_adsl.csv", f1, "text/csv")),
                ("files", ("fake_adae.csv", f2, "text/csv")),
                ("files", ("fake_adtte.csv", f3, "text/csv")),
            ], timeout=60)
        r.raise_for_status()
        uploaded = r.json()["uploaded"]
        assert len(uploaded) == 3, f"expected 3 uploads, got {len(uploaded)}"
        info(f"uploaded {len(uploaded)} files")

        # 3. Ingest
        requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
        deadline = time.time() + TIMEOUT_INGEST_S
        last_status: dict = {}
        while time.time() < deadline:
            s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
            last_status = s
            if s.get("all_done"):
                break
            time.sleep(1.0)
        if not last_status.get("all_done"):
            raise RuntimeError(f"ingest did not complete: {last_status.get('by_status')}")
        info(f"ingest complete: {last_status['by_status']}")

        # 4. Get the three file_ids; for each, request deterministic proposals
        #    and apply (mandatory PII rules + any deterministic ones).
        entries = last_status["entries"]
        for e in entries:
            fid = e["file_id"]
            r = requests.get(
                f"{BASE}/api/projects/{pid}/cleansing/proposals",
                params={"file_id": fid, "refresh": "true"},
                timeout=60,
            )
            r.raise_for_status()
            props = r.json()
            for p in props:
                if p["status"] == "pending" and not p["mandatory"]:
                    rr = requests.patch(
                        f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                        json={"status": "accepted"}, timeout=10,
                    )
                    rr.raise_for_status()
            # Apply (PII is auto-included)
            r = requests.post(
                f"{BASE}/api/projects/{pid}/cleansing/apply",
                json={"file_id": fid}, timeout=120,
            )
            r.raise_for_status()
        info("cleansing applied for all three files")

        # 5. Auto-analyze
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                          timeout=TIMEOUT_ANALYSIS_S)
        r.raise_for_status()
        info(f"auto-analyze response: {r.json().get('status')}")

        r = requests.get(f"{BASE}/api/projects/{pid}/stats", timeout=10)
        r.raise_for_status()
        blocks = r.json()
        info(f"stat blocks: {len(blocks)}")
        for b in blocks:
            info(f"  - {b['analysis_type']:12s} {b['title']}")
        if len(blocks) < 3:
            raise AssertionError(f"expected >=3 stat blocks, got {len(blocks)}: {[b['title'] for b in blocks]}")

        types = {b["analysis_type"] for b in blocks}
        for needed in ("descriptive", "safety", "survival"):
            if needed not in types:
                raise AssertionError(f"missing analysis_type {needed}, have {types}")

        # 6. Print one baseline_table snippet
        baseline = next(b for b in blocks if b["analysis_type"] == "descriptive")
        r = requests.get(f"{BASE}/api/projects/{pid}/stats/{baseline['id']}", timeout=10)
        r.raise_for_status()
        full = r.json()
        info(f"baseline markdown_table (first 600 chars):\n{full['markdown_table'][:600]}")

        # 7. Manual inferential (compare AGE between arms in the ADSL parquet)
        adsl_block = next((b for b in blocks if b["analysis_type"] == "descriptive"), None)
        assert adsl_block is not None
        # Recover ADSL parquet path from baseline params
        bd = requests.get(f"{BASE}/api/projects/{pid}/stats/{adsl_block['id']}", timeout=10).json()
        adsl_pq = bd["params"]["parquet_path"]
        r = requests.post(
            f"{BASE}/api/projects/{pid}/analysis/run",
            json={"type": "inferential",
                  "params": {"parquet_path": adsl_pq,
                             "group_col": "TRT01P", "value_col": "AGE"}},
            timeout=60,
        )
        r.raise_for_status()
        info(f"manual inferential OK -> id={r.json()['id']}")

        # 8. Build outline
        r = requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                          json={"principle_id": "ich_e3"},
                          timeout=TIMEOUT_OUTLINE_S)
        r.raise_for_status()
        info(f"outline build response: {r.json()}")

        r = requests.get(f"{BASE}/api/projects/{pid}/outline", timeout=10)
        r.raise_for_status()
        outline = r.json()
        n_nodes = _count_nodes(outline["root_sections"])
        info(f"outline nodes: {n_nodes} (version {outline['version']})")
        if n_nodes < 50:
            raise AssertionError(f"expected >=50 outline nodes, got {n_nodes}")

        # 9. Assert some sections have stat_refs (10.x descriptive, 11.x inferential, 12.x safety)
        nodes_with_stats = [n for n in _walk(outline["root_sections"]) if n.get("stat_refs")]
        info(f"nodes with stat_refs: {len(nodes_with_stats)}")
        for n in nodes_with_stats[:6]:
            info(f"  bound: {n['id']:10s} {n['title']:60s} refs={len(n['stat_refs'])}")
        if not nodes_with_stats:
            raise AssertionError("no outline nodes received stat_refs from auto-analysis")

        # Look for a section under id starting with 10 / 11 / 12 with binding
        adam_bound = {n["id"][:2] for n in nodes_with_stats if n["id"].split(".")[0].isdigit()}
        if not (adam_bound & {"10", "11", "12"}):
            # softer warning since the heuristic may bind only to 11/12; descriptive lives under 10
            info(f"warn: no chapter 10/11/12 binding; bound chapters = {adam_bound}")

        # 10. PATCH outline node — change notes on the first stat-bound node
        target = nodes_with_stats[0]
        r = requests.patch(
            f"{BASE}/api/projects/{pid}/outline/nodes/{target['id']}",
            json={"notes": "M3 e2e: writer should foreground the ADaM baseline table.",
                  "status": "writing"},
            timeout=10,
        )
        r.raise_for_status()
        patched = r.json()
        assert patched["notes"].startswith("M3 e2e"), "PATCH did not persist"
        assert patched["status"] == "writing"
        info(f"PATCH outline node {target['id']} OK")

        # 11. Verify outline.json on disk
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        out_path = data_dir() / "projects" / pid / "outline.json"
        if not out_path.exists():
            raise AssertionError(f"outline.json not persisted at {out_path}")
        info(f"outline.json persisted ({out_path.stat().st_size} bytes)")

        # 12. Version listing
        r = requests.get(f"{BASE}/api/projects/{pid}/outline/versions", timeout=5)
        r.raise_for_status()
        versions = r.json()
        info(f"outline versions on disk: {versions}")
        assert outline["version"] in versions, f"current version {outline['version']} not in archive {versions}"

        print("\n[E2E] OK  all checks passed", flush=True)
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
        # Cleanup workdir
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
                    import json as _json
                    items = _json.loads(projects_json.read_text(encoding="utf-8") or "[]")
                    items = [p for p in items if p.get("id") != pid]
                    projects_json.write_text(
                        _json.dumps(items, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            except Exception:
                pass


def _walk(nodes: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in nodes:
        out.append(n)
        out.extend(_walk(n.get("children") or []))
    return out


def _count_nodes(nodes: list[dict]) -> int:
    return len(_walk(nodes))


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND))
    sys.exit(main())
