"""End-to-end test for V2-E / M14 — medical coding + advanced stats + TLF export.

Flow:
  1.  GET /coding/systems → ≥6 systems; ≥3 CC0 (ICD-10/ATC/LOINC) available=true
  2.  POST /coding/lookup {system:'ICD10', term:'diabetes'} → candidates contain E10/E11
  3.  Build a synthetic ADAE CSV (AETERM column) + ADSL parquet (TRT01P/AGE/HEIGHT/WEIGHT/SEX/AGEGR1/AVAL)
      → upload + ingest → cleansing proposals include map_to_cdisc
  4.  Accept + apply cleansing → processed parquet contains AETERM_CODE column
  5.  POST /analysis/baseline_balance → StatBlock with SMD table
  6.  POST /analysis/subgroup → StatBlock with forest PNG
  7.  POST /analysis/multitest → StatBlock with FDR-adjusted p
  8.  POST /analysis/consort → StatBlock with mermaid + PNG
  9.  POST /analysis/sensitivity → ≥3 StatBlocks
  10. POST /export/tlf → zip > 5KB, contains ≥5 RTF + ≥5 CSV + define.xml
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8786"


def info(msg: str) -> None:
    print(f"[E2E-M14] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8786")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8786",
        "--host", "127.0.0.1", "--log-level", "warning",
    ]
    proc = subprocess.Popen(
        args, cwd=BACKEND, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
    raise RuntimeError("server did not come up")


def stop_server(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cleanup_project(pid: str) -> None:
    try:
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
        pj = data_dir() / "projects.json"
        if pj.exists():
            items = json.loads(pj.read_text(encoding="utf-8") or "[]")
            items = [p for p in items if p.get("id") != pid]
            pj.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def build_adsl_csv(path: Path, n: int = 120) -> None:
    """Synthesize an ADSL-ish CSV with TRT01P + demographics + AVAL + AETERM."""
    import csv
    import random
    random.seed(2026)
    sample_ae = ["头痛", "恶心", "皮疹", "腹泻", "失眠", "Fatigue", "Vomiting", "Cough", "Rash", "Dizziness"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["USUBJID", "TRT01P", "TRT01A", "AGE", "HEIGHT", "WEIGHT",
                     "SEX", "AGEGR1", "AVAL", "COMPFL", "RANDFL", "SAFFL",
                     "AETERM", "DCREASCD"])
        for i in range(n):
            arm = "A" if i % 2 == 0 else "B"
            age = round(random.gauss(55, 10), 1)
            ag = "<65" if age < 65 else ">=65"
            comp = "Y" if random.random() < 0.85 else "N"
            dc = "" if comp == "Y" else "ADVERSE EVENT"
            ae = random.choice(sample_ae)
            w.writerow([
                f"S{i:04d}", arm, arm,
                age,
                round(random.gauss(170, 8), 1),
                round(random.gauss(72, 12), 1),
                "M" if random.random() < 0.5 else "F",
                ag,
                round(random.gauss(0.5 if arm == "A" else 0.0, 3.0), 3),
                comp, "Y", "Y",
                ae,
                dc,
            ])


def assert_zip_ok(zpath: Path) -> dict:
    with zipfile.ZipFile(zpath, "r") as zf:
        names = zf.namelist()
        rtfs = [n for n in names if n.endswith(".rtf")]
        csvs = [n for n in names if n.endswith(".csv")]
        has_define = any(n == "define.xml" for n in names)
        has_manifest = any(n == "manifest.json" for n in names)
    return {"size": zpath.stat().st_size, "rtf": len(rtfs), "csv": len(csvs),
            "define": has_define, "manifest": has_manifest, "names": names}


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m14_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8786\n",
        encoding="utf-8",
    )

    proc = None
    pid: str | None = None
    try:
        # --- start server -------------------------------------------------
        proc = start_server(env)

        # --- 1. coding/systems ---------------------------------------------
        r = requests.get(f"{BASE}/api/coding/systems", timeout=10)
        r.raise_for_status()
        sys_list = r.json()
        info(f"coding systems: {len(sys_list)}  available={[s['id'] for s in sys_list if s['available']]}")
        assert len(sys_list) >= 6, f"expected ≥6 systems, got {len(sys_list)}"
        cc0_avail = [s for s in sys_list if s["id"] in ("ICD10", "ATC", "LOINC") and s["available"]]
        assert len(cc0_avail) >= 3, f"expected ICD10/ATC/LOINC all available, got {cc0_avail}"

        # --- 2. ICD10 lookup ----------------------------------------------
        r = requests.post(f"{BASE}/api/coding/lookup",
                          json={"system": "ICD10", "term": "diabetes", "top_k": 5}, timeout=10)
        r.raise_for_status()
        cands = r.json()["candidates"]
        info(f"ICD10 'diabetes' top: {[(c['code'], c['preferred_term']) for c in cands[:3]]}")
        assert any(c["code"] in ("E10", "E11") for c in cands), f"missing E10/E11: {cands}"

        # --- 3. create project + upload ADSL CSV --------------------------
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_m14", "principle_id": "ich_e3",
                                "language": "zh"}, timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"created project {pid}")

        adsl = workdir / "adsl.csv"
        build_adsl_csv(adsl, n=120)
        with adsl.open("rb") as f:
            requests.post(f"{BASE}/api/projects/{pid}/upload",
                          files=[("files", ("adsl.csv", f, "text/csv"))],
                          timeout=60).raise_for_status()
        requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
        deadline = time.time() + 180
        entries: list[dict] = []
        while time.time() < deadline:
            s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
            if s.get("all_done"):
                entries = s["entries"]
                break
            time.sleep(1.0)
        info(f"ingest done: {[(e['filename'], e['ingest_type']) for e in entries]}")
        assert entries, "no ingest entries"
        fid = entries[0]["file_id"]

        # --- cleansing proposals: expect map_to_cdisc ---------------------
        proposals = requests.get(
            f"{BASE}/api/projects/{pid}/cleansing/proposals",
            params={"file_id": fid, "refresh": "true"}, timeout=120,
        ).json()
        types = sorted({p["type"] for p in proposals})
        info(f"proposals: {len(proposals)} types={types}")
        mtc = [p for p in proposals if p["type"] == "map_to_cdisc"]
        assert mtc, f"expected map_to_cdisc proposal, got types={types}"
        mtc_p = mtc[0]
        info(f"map_to_cdisc on column {mtc_p['target_columns']} system={mtc_p['parameters'].get('system')} "
             f"n_terms={len(mtc_p['parameters'].get('mappings') or [])}")
        # Pick top candidate for each term as user selection (simulating UI)
        selections = {}
        for m in mtc_p["parameters"].get("mappings", []):
            if m["candidates"]:
                selections[m["original"]] = m["candidates"][0]["code"]
        # Update the proposal with user_selections + accept
        new_params = {**mtc_p["parameters"], "user_selections": selections}
        requests.patch(
            f"{BASE}/api/projects/{pid}/cleansing/proposals/{mtc_p['id']}",
            json={"parameters": new_params, "status": "accepted"}, timeout=10,
        ).raise_for_status()

        # Accept all other non-pending non-rejected proposals so apply has work
        for p in proposals:
            if p["id"] == mtc_p["id"]:
                continue
            if p["status"] != "pending":
                continue
            requests.patch(
                f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                json={"status": "accepted"}, timeout=10,
            ).raise_for_status()

        apply_res = requests.post(f"{BASE}/api/projects/{pid}/cleansing/apply",
                                    json={"file_id": fid}, timeout=120).json()
        info(f"cleansing apply: rows_after={apply_res.get('rows_after')} applied={len(apply_res.get('applied', []))}")
        # Verify processed parquet has AETERM_CODE column
        prev = requests.get(f"{BASE}/api/projects/{pid}/cleansing/preview",
                              params={"file_id": fid, "n": 5}, timeout=10).json()
        cols = prev["columns"]
        info(f"processed columns: {cols}")
        assert "AETERM_CODE" in cols, f"AETERM_CODE not in processed cols: {cols}"
        assert "AETERM_PT" in cols, f"AETERM_PT not in processed cols: {cols}"

        # --- 5. baseline_balance -------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/baseline_balance",
                          json={"group_col": "TRT01P", "vars": ["AGE", "HEIGHT", "WEIGHT", "SEX"],
                                "file_id": fid}, timeout=60)
        r.raise_for_status()
        b = r.json()["block"]
        info(f"baseline_balance: n_vars={len(b['result_json'].get('variables', []))} "
             f"n_imbalanced={b['result_json'].get('n_imbalanced')}")
        assert b["result_json"].get("variables"), "no SMD variables"

        # --- 6. subgroup ---------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/subgroup",
                          json={"outcome_col": "AVAL", "group_col": "TRT01P",
                                "subgroup_cols": ["SEX", "AGEGR1"],
                                "file_id": fid}, timeout=60)
        r.raise_for_status()
        sg = r.json()["block"]
        info(f"subgroup: rows={len(sg['result_json'].get('rows', []))} "
             f"png={'yes' if sg['result_json'].get('png_path') else 'no'}")
        assert sg["result_json"].get("rows"), "no subgroup rows"

        # --- 7. multitest --------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/multitest",
                          json={"p_values": [0.01, 0.03, 0.05, 0.08, 0.10],
                                "method": "fdr_bh"}, timeout=15)
        r.raise_for_status()
        mt = r.json()["block"]
        info(f"multitest: adjusted={mt['result_json'].get('adjusted_p')} "
             f"n_rejected={mt['result_json'].get('n_rejected')}")
        assert mt["result_json"].get("adjusted_p"), "no adjusted_p"

        # --- 8. consort ----------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/consort",
                          json={}, timeout=30)
        r.raise_for_status()
        cs = r.json()["block"]
        info(f"consort: stages={cs['result_json'].get('stages')} "
             f"mermaid_lines={len(cs['result_json'].get('mermaid', '').splitlines())}")
        assert cs["result_json"].get("mermaid", "").startswith("graph"), "no mermaid"

        # --- 9. sensitivity (3 methods) -----------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/analysis/sensitivity",
                          json={"outcome_col": "AVAL", "group_col": "TRT01P",
                                "methods": ["itt", "pp", "locf"],
                                "file_id": fid}, timeout=60)
        r.raise_for_status()
        sens = r.json()
        info(f"sensitivity: n_blocks={sens['n']} ids={sens['ids']}")
        assert sens["n"] >= 3, f"expected ≥3 sensitivity blocks, got {sens['n']}"

        # --- 10. TLF export ------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/export/tlf", timeout=300)
        r.raise_for_status()
        tlf = r.json()
        info(f"tlf zip: {tlf['filename']} size={tlf['size_bytes']}")

        # Download + inspect
        r = requests.get(f"{BASE}/api/projects/{pid}/exports/tlf/{tlf['filename']}", timeout=60)
        r.raise_for_status()
        out = workdir / tlf["filename"]
        out.write_bytes(r.content)
        verdict = assert_zip_ok(out)
        info(f"tlf verify: size={verdict['size']} rtf={verdict['rtf']} csv={verdict['csv']} "
             f"define={verdict['define']} manifest={verdict['manifest']}")
        assert verdict["size"] > 5_000, f"zip too small: {verdict['size']}"
        assert verdict["rtf"] >= 5, f"expected ≥5 RTF, got {verdict['rtf']}"
        assert verdict["csv"] >= 5, f"expected ≥5 CSV, got {verdict['csv']}"
        assert verdict["define"], "missing define.xml"

        print("\n[E2E-M14] OK  all checks passed", flush=True)
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
        if pid:
            cleanup_project(pid)
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


if __name__ == "__main__":
    sys.exit(main())
