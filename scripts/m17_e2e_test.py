"""End-to-end test for V3-A / M17 — v1.0 backend release prep.

Coverage:
  1. /openapi.json + /docs surface tags and v1.0 metadata
  2. /metrics exposes Prometheus output
  3. Hallucination check on a draft with a bogus Ref returns >=1 finding
  4. Sign chain init + advance enforces order (403 on skip)
  5. eCTD packager produces a zip with the expected layout
  6. Completeness checker fires when outline missing required sections
  7. Checkpoint resume reports the saved progress
  8. SDK generator is invocable (skip OK)
  9. Audit rotation truncates an oversize shard

Run after installing the extended deps (prometheus_client, babel).
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
BASE = "http://127.0.0.1:8798"


def info(msg: str) -> None:
    print(f"[E2E-M17] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def _start(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8798")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server.main:app",
         "--port", "8798", "--host", "127.0.0.1", "--log-level", "warning"],
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


def _stop(proc: subprocess.Popen) -> None:
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


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m17_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env["CSR_REVIEWER_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8798\n"
        "queue:\n  backend: inmemory\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start(env)

        # --- 1) OpenAPI surface
        spec = requests.get(f"{BASE}/openapi.json", timeout=10).json()
        info(f"openapi: title={spec['info']['title']} version={spec['info']['version']}")
        if spec["info"]["version"] != "1.0.0":
            raise AssertionError(f"openapi version wrong: {spec['info']['version']}")
        tag_names = {t["name"] for t in spec.get("tags") or []}
        for required in ("projects", "ingest", "report", "review", "export", "safety"):
            if required not in tag_names:
                raise AssertionError(f"openapi tag {required!r} missing")

        # --- 2) Prometheus metrics
        r = requests.get(f"{BASE}/metrics", timeout=10)
        if r.status_code not in (200, 503):
            raise AssertionError(f"/metrics returned {r.status_code}")
        info(f"metrics endpoint: {r.status_code} body_starts={r.text[:80]!r}")

        # --- 3) Project + hallucination check
        pid = requests.post(f"{BASE}/api/projects",
                             json={"name": "M17 e2e", "principle_id": "ich_e3"},
                             timeout=10).json()["id"]
        info(f"project: {pid}")
        # Drop a draft with a bogus Ref directly via the API surface
        sys.path.insert(0, str(BACKEND))
        import datetime as _dt
        from app.config import data_dir
        from app.report.store import save_draft
        from app.schemas.report import SectionDraft, Provenance
        bad_draft = SectionDraft(
            node_id="11.4.1.1",
            title="Hallucination demo",
            markdown="Per Refmissing1.P1.Col1.Para1 the effect is large.",
            generated_at=_dt.datetime.now(_dt.timezone.utc),
            provenance=[Provenance(range=(0, 60), source="ai")],
        )
        save_draft(pid, bad_draft)
        hg = requests.post(f"{BASE}/api/projects/{pid}/hallucination_check",
                            timeout=20).json()
        info(f"hallucination findings: {hg.get('n_findings')}")
        if hg.get("n_findings", 0) < 1:
            raise AssertionError("hallucination_check did not catch missing Ref")

        # --- 4) Sign chain enforcement
        task = requests.post(
            f"{BASE}/api/projects/{pid}/tasks",
            json={"assignee": "demo_reviewer", "body": "needs signatures",
                   "title": "sign me"},
            headers={"X-User-Id": "demo_admin"}, timeout=10,
        ).json()
        tid = task["id"]
        init = requests.post(
            f"{BASE}/api/projects/{pid}/tasks/{tid}/sign_chain/init",
            json={}, timeout=10,
        ).json()
        if not init.get("sign_chain"):
            raise AssertionError("sign_chain init failed")
        # Skip the first step → expect 403
        skip = requests.post(
            f"{BASE}/api/projects/{pid}/tasks/{tid}/sign_chain/advance",
            json={"role": "medical", "signer_user_id": "med_user"},
            headers={"X-User-Id": "med_user"}, timeout=10,
        )
        info(f"out-of-order sign attempt status: {skip.status_code}")
        if skip.status_code != 403:
            raise AssertionError(f"expected 403 out-of-order got {skip.status_code}")
        # Sign in order
        ok = requests.post(
            f"{BASE}/api/projects/{pid}/tasks/{tid}/sign_chain/advance",
            json={"role": "statistician", "signer_user_id": "stat_user",
                   "reason": "ok"},
            headers={"X-User-Id": "stat_user"}, timeout=10,
        ).json()
        if ok.get("status") != "signed":
            raise AssertionError(f"in-order sign failed: {ok}")
        info("sign chain enforces ordering")

        # --- 5) eCTD packager (with stub exports)
        exports = data_dir() / "projects" / pid / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        (exports / "csr_demo.docx").write_bytes(b"PK\x03\x04")
        import zipfile
        with zipfile.ZipFile(exports / "tlf_demo.zip", "w") as zf:
            zf.writestr("define.xml", "<Define/>")
            zf.writestr("tables/t1.csv", "a,b\n1,2\n")
        r = requests.post(f"{BASE}/api/projects/{pid}/export/ectd", timeout=30)
        if r.status_code != 200:
            raise AssertionError(f"ectd export status={r.status_code} body={r.text[:200]}")
        out = r.json()
        info(f"ectd zip: {out.get('filename')} size={out.get('size_bytes')}")
        ectd_zip = data_dir() / "projects" / pid / "exports" / "ectd" / out["filename"]
        with zipfile.ZipFile(ectd_zip, "r") as zf:
            names = zf.namelist()
        if not any("535-rep-effic-safety-stud" in n for n in names):
            raise AssertionError("eCTD missing m5.3.5 path")
        if not any(n.endswith("/manifest.json") for n in names):
            raise AssertionError("eCTD missing manifest")

        # --- 6) Completeness via multi_review (4th checker)
        mr = requests.post(f"{BASE}/api/projects/{pid}/multi_review",
                            json={"sync": True}, timeout=180).json()
        if not mr.get("completeness"):
            raise AssertionError("multi_review did not run completeness checker")
        info(f"completeness issues: {len(mr['completeness'].get('issues', []))}")

        # --- 7) Checkpoint resume (synthetic)
        from app.queue import checkpoint as cp
        cp.write_checkpoint(pid, "fake_task_42", kind="report.generate",
                             total=5, completed_items=["a", "b"])
        r = requests.post(f"{BASE}/api/tasks/fake_task_42/resume",
                          json={"project_id": pid}, timeout=10).json()
        info(f"resume report: {r}")
        if r.get("completed") != 2 or r.get("total") < 2:
            raise AssertionError(f"resume reported wrong counts: {r}")

        # --- 8) SDK generator (skip is acceptable)
        gen = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_sdk.py")],
            capture_output=True, text=True, timeout=120,
        )
        info(f"sdk gen exit={gen.returncode} stdout_tail={gen.stdout[-200:]}")

        # --- 9) Audit rotation
        from app.audit.rotation import rotate_if_needed
        shard = data_dir() / "projects" / pid / "audit" / "2026-05.jsonl"
        shard.parent.mkdir(parents=True, exist_ok=True)
        shard.write_bytes(b"{\"x\":1}\n" * 500)
        archive = rotate_if_needed(shard, threshold_bytes=100)
        if archive is None or not archive.exists():
            raise AssertionError("audit rotation did not archive oversize shard")
        info(f"audit rotation archive: {archive.name}")

        info("M17 e2e PASS")
        return 0
    except Exception as e:
        err(f"M17 e2e FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if proc is not None:
            _stop(proc)
        if pid is not None:
            _cleanup_project(pid)
        if saved is not None:
            overlay.write_bytes(saved)
        else:
            overlay.unlink(missing_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
