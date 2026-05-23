"""End-to-end test for v2.1.0 P0 audit fixes.

Coverage:

    1. GET /api/projects returns records that carry the M21 multi-tenant
       fields (`tenant_id`, `created_by`) — confirms backend → frontend
       schema sync (frontend `ProjectDTO` was missing these pre-v2.1).
    2. POST /api/projects/{pid}/literature_search with an unknown source
       returns a 4xx (not 500) and the error payload references the
       `AgentError` path (was a bare `ValueError → 500` before v2.1).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BASE = "http://127.0.0.1:8799"


def info(msg: str) -> None:
    print(f"[E2E-V21] {msg}", flush=True)


def _start(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8799")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.server.main:app",
         "--port", "8799", "--host", "127.0.0.1", "--log-level", "warning"],
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


def main() -> int:
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8799\n"
        "queue:\n  backend: inmemory\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start(env)

        # 1) Create a project + verify M21 fields land in /projects list.
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "v21_dto_check",
                                "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"created project: {pid}")

        listing = requests.get(f"{BASE}/api/projects", timeout=10).json()
        target = next((p for p in listing if p.get("id") == pid), None)
        if target is None:
            raise AssertionError(f"project {pid} not found in listing")
        if "tenant_id" not in target:
            raise AssertionError(
                f"ProjectDTO missing tenant_id field: keys={list(target.keys())}")
        if "created_by" not in target:
            raise AssertionError(
                f"ProjectDTO missing created_by field: keys={list(target.keys())}")
        info(f"  tenant_id={target['tenant_id']} created_by={target['created_by']}")

        # 2) literature_search with bad source → 4xx + agent_error signal.
        r = requests.post(
            f"{BASE}/api/projects/{pid}/literature_search",
            json={"query": "test", "source": "invalid_source"},
            timeout=15,
        )
        info(f"  literature_search invalid_source → HTTP {r.status_code}")
        if r.status_code >= 500:
            raise AssertionError(
                f"expected 4xx for unknown source, got {r.status_code}: "
                f"{r.text[:200]}")
        if r.status_code < 400:
            raise AssertionError(
                f"expected 4xx for unknown source, got {r.status_code}")
        payload = r.json()
        detail = str(payload.get("detail") or "")
        if "agent_error" not in detail and "unknown source" not in detail:
            raise AssertionError(
                f"expected agent_error / unknown source in detail, got: {detail}")
        info(f"  detail contains expected marker: {detail[:120]}")

        info("OK — v2.1.0 P0 checks passed")
        return 0
    finally:
        if proc is not None:
            _stop(proc)
        if saved is not None:
            overlay.write_bytes(saved)
        else:
            try:
                overlay.unlink()
            except FileNotFoundError:
                pass
        if pid:
            try:
                sys.path.insert(0, str(BACKEND))
                from app.config import data_dir
                import shutil
                shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
                pj = data_dir() / "projects.json"
                if pj.exists():
                    items = json.loads(pj.read_text(encoding="utf-8") or "[]")
                    items = [p for p in items if p.get("id") != pid]
                    pj.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
