"""End-to-end test for V2-D / M12 — project mgmt + templates + state summary.

Smoke-checks:
  1. GET /api/templates  → 4 presets
  2. POST /api/projects/from_template/<id>   for each of the 4 presets
  3. PATCH /api/projects/<pid>               tags + archived
  4. GET  /api/projects?search=...           filters correctly
  5. GET  /api/projects?tag=...              filters correctly
  6. GET  /api/projects?archived=false       hides archived
  7. DELETE /api/projects/<pid>              works once archived
  8. GET  /api/projects/<pid>/state_summary  returns step counters
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8780"

TEMPLATE_IDS = ["standard_ich_e3", "phase_i_fih", "post_marketing", "tcm"]


def info(msg: str) -> None:
    print(f"[E2E-M12] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8780")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8780",
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
        import shutil
        import json as _json
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
        pj = data_dir() / "projects.json"
        if pj.exists():
            items = _json.loads(pj.read_text(encoding="utf-8") or "[]")
            items = [p for p in items if p.get("id") != pid]
            pj.write_text(_json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8780\n",
        encoding="utf-8",
    )

    proc = None
    created_pids: list[str] = []
    try:
        proc = start_server(env)

        # 1. /api/templates returns 4 presets ---------------------------------
        r = requests.get(f"{BASE}/api/templates", timeout=5)
        r.raise_for_status()
        templates = r.json()
        info(f"templates: {[t['id'] for t in templates]}")
        ids = {t["id"] for t in templates}
        for tid in TEMPLATE_IDS:
            if tid not in ids:
                raise AssertionError(f"template {tid} missing from /api/templates")

        # 2. create one project per template ----------------------------------
        for tid in TEMPLATE_IDS:
            r = requests.post(
                f"{BASE}/api/projects/from_template/{tid}",
                json={"name": f"e2e_m12_{tid}"}, timeout=10,
            )
            r.raise_for_status()
            p = r.json()
            created_pids.append(p["id"])
            tpl = next(t for t in templates if t["id"] == tid)
            assert p["principle_id"] == tpl["principle_id"], \
                f"principle mismatch for {tid}: {p['principle_id']} vs {tpl['principle_id']}"
            assert p["template_id"] == tid
            assert p["language"] == tpl["language"]
            assert isinstance(p.get("tags"), list) and len(p["tags"]) >= 1
            info(f"created from {tid}: pid={p['id']} tags={p['tags']}")

        first_pid = created_pids[0]

        # 3. PATCH tags --------------------------------------------------------
        r = requests.patch(f"{BASE}/api/projects/{first_pid}",
                            json={"tags": ["demo", "test"]}, timeout=5)
        r.raise_for_status()
        assert set(r.json()["tags"]) == {"demo", "test"}
        info(f"patched tags on {first_pid}")

        # 4. search by name fragment ------------------------------------------
        r = requests.get(f"{BASE}/api/projects",
                          params={"search": "phase"}, timeout=5)
        r.raise_for_status()
        hits = r.json()
        info(f"search 'phase': {len(hits)} hits")
        assert any("phase" in p["name"].lower() for p in hits), \
            f"expected hits containing 'phase' in name, got names {[p['name'] for p in hits]}"

        # 5. filter by tag -----------------------------------------------------
        r = requests.get(f"{BASE}/api/projects",
                          params={"tag": "demo"}, timeout=5)
        r.raise_for_status()
        tag_hits = r.json()
        info(f"tag=demo: {len(tag_hits)} hits")
        assert any(p["id"] == first_pid for p in tag_hits), \
            f"first_pid {first_pid} not in tag=demo filter"

        # 6. archive + filter --------------------------------------------------
        r = requests.patch(f"{BASE}/api/projects/{first_pid}",
                            json={"archived": True}, timeout=5)
        r.raise_for_status()
        assert r.json()["archived"] is True
        r = requests.get(f"{BASE}/api/projects",
                          params={"archived": "false"}, timeout=5)
        r.raise_for_status()
        unarchived = r.json()
        assert all(p["id"] != first_pid for p in unarchived), \
            f"archived project leaked into archived=false list"
        info(f"after archive+filter: {len(unarchived)} visible (excludes {first_pid})")

        # 7. delete the archived project --------------------------------------
        r = requests.delete(f"{BASE}/api/projects/{first_pid}", timeout=5)
        r.raise_for_status()
        info(f"deleted archived project {first_pid}")
        # confirm gone
        r = requests.get(f"{BASE}/api/projects/{first_pid}", timeout=5)
        assert r.status_code == 404
        # mark cleaned so the finally hook doesn't try again
        created_pids.remove(first_pid)

        # 8. state_summary on a fresh project ---------------------------------
        target = created_pids[0]
        r = requests.get(f"{BASE}/api/projects/{target}/state_summary", timeout=10)
        r.raise_for_status()
        summary = r.json()
        info(f"state_summary({target}): current_step={summary['current_step']} "
             f"intake={summary['steps']['intake']}")
        assert "steps" in summary
        for step in ("intake", "cleanse", "analyze", "outline", "report", "review", "export"):
            assert step in summary["steps"], f"missing step '{step}' in state_summary"

        # 9. blank project + delete-without-archive should 409 ----------------
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_m12_blank"}, timeout=5)
        r.raise_for_status()
        blank = r.json()["id"]
        created_pids.append(blank)
        r = requests.delete(f"{BASE}/api/projects/{blank}", timeout=5)
        assert r.status_code == 409, f"expected 409 deleting unarchived, got {r.status_code}"
        info("delete-without-archive correctly returned 409")
        # cleanup with force
        r = requests.delete(f"{BASE}/api/projects/{blank}",
                             params={"force": "true"}, timeout=5)
        assert r.status_code == 200
        created_pids.remove(blank)

        print("\n[E2E-M12] OK  all checks passed", flush=True)
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
        for pid in list(created_pids):
            cleanup_project(pid)
        try:
            if saved is None:
                if overlay.exists():
                    overlay.unlink()
            else:
                overlay.write_bytes(saved)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
