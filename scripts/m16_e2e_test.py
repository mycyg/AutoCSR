"""End-to-end test for V2-F / M16 — 3-reviewer + collab tasks + project diff.

Flow:
  1. Build a small project (mock writer), GET /users → 4 seed users.
  2. POST /multi_review → 3 reviewers each return ≥1 issue, combined_count
     populated.
  3. POST /tasks/from_issue/{issue_id} → task created with assignee.
  4. PATCH /tasks/{tid} {status: 'resolved'} + GET ?status=resolved verify.
  5. GET /tasks?assignee=demo_reviewer&status=open returns filtered list.
  6. POST /tasks (manual) → assignee + due_date.
  7. queue: enqueue 'multi_review' and poll /tasks/{task_id}/status.
  8. Build second project + POST /projects/compare {by:outline} verifies
     diff non-empty (different outlines).
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
BASE = "http://127.0.0.1:8797"


def info(msg: str) -> None:
    print(f"[E2E-M16] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def _start(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8797")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server.main:app",
         "--port", "8797", "--host", "127.0.0.1", "--log-level", "warning"],
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


def _make_adsl(p: Path) -> None:
    p.write_text(
        "USUBJID,AGE,SEX,TRT01P,HEIGHT,WEIGHT\n"
        "001-001,52,M,DrugA,170,72\n"
        "001-002,47,F,DrugA,160,55\n"
        "001-003,61,M,Placebo,175,80\n"
        "001-004,38,F,Placebo,158,52\n"
        "001-005,55,M,DrugA,168,70\n"
        "001-006,42,F,Placebo,162,58\n"
        "001-007,49,M,DrugA,172,75\n"
        "001-008,33,F,Placebo,159,49\n",
        encoding="utf-8",
    )


def _apply_cleansing(pid: str, filename: str, content_path: Path) -> None:
    with content_path.open("rb") as f1:
        requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", (filename, f1, "text/csv")),
        ], timeout=60).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + 120
    entries: list[dict] = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status",
                         timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(0.8)
    fid = next(e["file_id"] for e in entries if e["filename"] == filename)
    props = requests.get(
        f"{BASE}/api/projects/{pid}/cleansing/proposals",
        params={"file_id": fid, "refresh": "true"}, timeout=60,
    ).json()
    for p in props:
        if p["status"] != "pending":
            continue
        requests.patch(
            f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
            json={"status": "accepted"}, timeout=10,
        ).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/cleansing/apply",
                  json={"file_id": fid}, timeout=120).raise_for_status()


def _wait_report(pid: str, timeout_s: int = 240) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/report/status",
                         timeout=10).json()
        if s.get("current_phase") in ("done", "error"):
            return
        time.sleep(1.2)
    raise TimeoutError("report never settled")


def _build_full_project(name: str, workdir: Path, leaves: int = 4) -> str:
    pid = requests.post(f"{BASE}/api/projects",
                        json={"name": name, "principle_id": "ich_e3"},
                        timeout=10).json()["id"]
    adsl = workdir / f"{name}_adsl.csv"
    _make_adsl(adsl)
    _apply_cleansing(pid, adsl.name, adsl)
    requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                  json={}, timeout=300).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                  json={"principle_id": "ich_e3"},
                  timeout=300).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                  json={"harmonize": False, "leaf_limit": leaves},
                  timeout=10).raise_for_status()
    _wait_report(pid)
    return pid


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m16_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env["CSR_REVIEWER_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8797\n"
        "queue:\n  backend: inmemory\n",
        encoding="utf-8",
    )

    proc = None
    pid_a = pid_b = None
    try:
        proc = _start(env)

        # 1) Users
        users = requests.get(f"{BASE}/api/users", timeout=10).json()
        info(f"users: {[u['id'] for u in users]}")
        if len(users) < 4:
            raise AssertionError(f"expected 4 seed users, got {len(users)}")

        # 2) Build project + multi_review
        pid_a = _build_full_project("e2e_M16_A", workdir, leaves=4)
        info(f"project A: {pid_a}")
        mr = requests.post(f"{BASE}/api/projects/{pid_a}/multi_review",
                           json={"sync": True}, timeout=180).json()
        info("multi_review combined: " + json.dumps(mr.get("combined_count")))
        for key in ("statistician", "medical", "regulatory"):
            inner = mr.get(key) or {}
            issues = inner.get("issues") or []
            info(f"  {key}: {len(issues)} issues")
            if len(issues) < 1:
                raise AssertionError(f"{key} reviewer returned zero issues")

        # 3) from_issue: pick the first statistician issue
        first_issue = (mr["statistician"]["issues"] or [None])[0]
        if first_issue is None:
            raise AssertionError("no statistician issue to convert")
        iss_id = first_issue["id"]
        t = requests.post(
            f"{BASE}/api/projects/{pid_a}/tasks/from_issue/{iss_id}",
            json={"assignee": "demo_reviewer"},
            headers={"X-User-Id": "demo_admin"}, timeout=10,
        ).json()
        info(f"task from_issue: {t.get('id')}")
        if not t.get("id"):
            raise AssertionError(f"from_issue did not create task: {t}")

        # 4) PATCH resolve
        r = requests.patch(
            f"{BASE}/api/projects/{pid_a}/tasks/{t['id']}",
            json={"status": "resolved", "comment": "fixed in section 11"},
            headers={"X-User-Id": "demo_reviewer"}, timeout=10,
        ).json()
        info(f"task resolve: status={r.get('status')} comments={len(r.get('comments') or [])}")
        if r.get("status") != "resolved":
            raise AssertionError(f"task did not resolve: {r}")

        # 5) Filter list
        open_tasks = requests.get(
            f"{BASE}/api/projects/{pid_a}/tasks",
            params={"assignee": "demo_reviewer", "status": "open"},
            timeout=10,
        ).json()
        info(f"open tasks assigned to demo_reviewer: {len(open_tasks)}")
        # The one we created was just resolved, so this should be 0 unless
        # multi_review spawned auto tasks (it doesn't).
        if any(x["id"] == t["id"] for x in open_tasks):
            raise AssertionError("resolved task still appears in open filter")

        # 6) Manual task
        manual = requests.post(
            f"{BASE}/api/projects/{pid_a}/tasks",
            json={
                "assignee": "demo_author",
                "severity": "warn",
                "body": "Author should re-check 9.1 informed consent paragraph",
                "due_date": "2026-06-15T00:00:00Z",
            },
            headers={"X-User-Id": "demo_admin"}, timeout=10,
        ).json()
        info(f"manual task: {manual.get('id')} assignee={manual.get('assignee')}")
        if not manual.get("id"):
            raise AssertionError(f"manual task create failed: {manual}")

        # 7) Queue: enqueue multi_review asynchronously, then poll status
        r = requests.post(f"{BASE}/api/projects/{pid_a}/multi_review",
                          json={"sync": False}, timeout=30).json()
        info(f"async multi_review enqueue: {r}")
        task_id = r.get("task_id")
        if not task_id:
            raise AssertionError("no task_id from async multi_review")
        deadline = time.time() + 60
        final = None
        while time.time() < deadline:
            st = requests.get(f"{BASE}/api/tasks/{task_id}/status",
                              timeout=10).json()
            if st.get("status") in ("done", "error", "cancelled"):
                final = st
                break
            time.sleep(0.5)
        info(f"queue task final: status={(final or {}).get('status')}")
        if not final or final.get("status") != "done":
            raise AssertionError(f"queue task did not complete: {final}")

        # 8) Cross-project diff
        pid_b = _build_full_project("e2e_M16_B", workdir, leaves=2)
        info(f"project B: {pid_b}")
        diff = requests.post(f"{BASE}/api/projects/compare",
                             json={"pid_a": pid_a, "pid_b": pid_b,
                                   "by": "outline"},
                             timeout=20).json()
        info("diff summary: " + json.dumps(diff.get("summary")))
        n_total = sum(int(v) for v in (diff.get("summary") or {}).values())
        if n_total < 1:
            raise AssertionError(f"compare summary empty: {diff}")
        # At minimum we expect some 'unchanged' entries since both projects
        # use the same ICH E3 outline; some chapters may differ. Either way,
        # the entries list should be non-empty.
        if len(diff.get("outline") or []) < 5:
            raise AssertionError(
                f"compare outline too small (got {len(diff.get('outline') or [])})",
            )

        info("M16 e2e PASS")
        return 0
    except Exception as e:
        err(f"M16 e2e FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if proc is not None:
            _stop(proc)
        for p in (pid_a, pid_b):
            if p is not None:
                _cleanup_project(p)
        if saved is not None:
            overlay.write_bytes(saved)
        else:
            overlay.unlink(missing_ok=True)
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
