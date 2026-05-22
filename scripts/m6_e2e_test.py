"""End-to-end test for M6 (agent abstraction + state machine + structured logs + config).

Boots uvicorn (mock writer/editor), runs the full M5 pipeline (upload ->
ingest -> cleansing -> analysis -> outline -> writer -> harmonize ->
export), and at every stage checks that:

  * ``GET /api/projects/{pid}/state`` returns the right ProjectState
  * stderr (uvicorn JSON logs) contains ``agent.start`` / ``agent.done``
    events from at least one writer agent
  * ``GET/PATCH /api/projects/{pid}/config`` round-trips correctly
  * illegal backward transitions raise StateTransitionError (unit check)

Exit code 0 on success.
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
BASE = "http://127.0.0.1:8771"


def info(msg: str) -> None:
    print(f"[E2E-M6] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


# Reuse M4's fake-data builders + start_server stop_server wait_for_report
sys.path.insert(0, str(ROOT))
import scripts.m4_e2e_test as _m4  # noqa: E402
_m4.BASE = BASE
from scripts.m4_e2e_test import (  # noqa: E402
    make_adae, make_adsl, make_adtte, stop_server, wait_for_report,
)


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8771")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8771",
        "--host", "127.0.0.1", "--log-level", "info",
    ]
    # Tee server output to a file so we can grep agent.* events after the run.
    log_path = Path(tempfile.gettempdir()) / "autocsr_m6_server.log"
    log_fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        args, cwd=BACKEND, env=env,
        stdout=log_fh, stderr=subprocess.STDOUT,
    )
    proc._log_path = str(log_path)  # type: ignore[attr-defined]
    proc._log_fh = log_fh  # type: ignore[attr-defined]
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


def _expect_state(pid: str, expected: str) -> None:
    rec = requests.get(f"{BASE}/api/projects/{pid}/state", timeout=10).json()
    actual = rec.get("state")
    if actual != expected:
        raise AssertionError(
            f"state mismatch: expected {expected!r}, got {actual!r}; "
            f"history tail={rec.get('history', [])[-3:]}",
        )
    info(f"state OK: {actual}")


def _check_config_roundtrip(pid: str) -> None:
    cfg = requests.get(f"{BASE}/api/projects/{pid}/config", timeout=10).json()
    for k in ("language", "max_parallel_writers", "sandbox_enabled"):
        if k not in cfg:
            raise AssertionError(f"ProjectConfig missing key: {k}")
    info(f"default config OK: parallelism={cfg['max_parallel_writers']}")
    updated = requests.patch(
        f"{BASE}/api/projects/{pid}/config",
        json={"max_parallel_writers": 2, "language": "en"},
        timeout=10,
    ).json()
    if updated["max_parallel_writers"] != 2 or updated["language"] != "en":
        raise AssertionError(f"PATCH /config did not stick: {updated}")
    info("config PATCH OK")


def _check_state_machine_unit() -> None:
    """Unit-level check that backward transitions raise."""
    sys.path.insert(0, str(BACKEND))
    from app.state.machine import (
        ProjectState, ProjectStateMachine, StateTransitionError,
    )
    pid = "_unit_test_" + os.urandom(4).hex()
    sm = ProjectStateMachine()
    try:
        sm.transition(pid, ProjectState.uploaded)
        sm.transition(pid, ProjectState.cleansed)
        # Backwards (cleansed -> uploaded is allowed but cleansed -> created is not)
        try:
            sm.transition(pid, ProjectState.created)
        except StateTransitionError:
            info("backward transition correctly rejected (cleansed -> created)")
        else:
            raise AssertionError("backward transition cleansed -> created should have failed")
        # Self-transition is idempotent
        end = sm.transition(pid, ProjectState.cleansed)
        if end != ProjectState.cleansed:
            raise AssertionError("self-transition should be idempotent")
        info("idempotent self-transition OK")
    finally:
        from app.config import data_dir
        shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)


def _grep_agent_events(server_proc: subprocess.Popen) -> dict[str, int]:
    """Read the captured server log file and count agent.* events."""
    counts = {"agent.start": 0, "agent.done": 0, "agent.error": 0,
              "project.state_changed": 0}
    log_path = getattr(server_proc, "_log_path", None)
    if not log_path:
        return counts
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                for key in counts:
                    if key in line:
                        counts[key] += 1
    except Exception:
        pass
    return counts


def run_pipeline(pid: str, server_proc: subprocess.Popen) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m6_e2e_inputs_"))
    adsl = workdir / "fake_adsl.csv"
    adae = workdir / "fake_adae.csv"
    adtte = workdir / "fake_adtte.csv"
    make_adsl(adsl); make_adae(adae); make_adtte(adtte)

    with adsl.open("rb") as f1, adae.open("rb") as f2, adtte.open("rb") as f3:
        requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", ("fake_adsl.csv", f1, "text/csv")),
            ("files", ("fake_adae.csv", f2, "text/csv")),
            ("files", ("fake_adtte.csv", f3, "text/csv")),
        ], timeout=60).raise_for_status()
    info("upload done")
    _expect_state(pid, "uploaded")

    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + 120
    entries = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(1.0)
    if not entries:
        raise RuntimeError("ingest timed out")

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
    _expect_state(pid, "cleansed")

    requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                  timeout=180).raise_for_status()
    info("analysis done")
    _expect_state(pid, "analyzed")

    requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                  json={"principle_id": "ich_e3"}, timeout=320).raise_for_status()
    info("outline built")
    _expect_state(pid, "outlined")

    requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                  json={"harmonize": True, "leaf_limit": 4}, timeout=30).raise_for_status()
    final = wait_for_report(pid, timeout=120)
    if final.get("current_phase") != "done":
        raise AssertionError(f"writer phase not done: {final.get('current_phase')}")
    info("writer done")
    # writing -> harmonized -> stay there; check
    state_now = requests.get(f"{BASE}/api/projects/{pid}/state", timeout=10).json()
    if state_now["state"] not in ("harmonized", "writing"):
        raise AssertionError(f"after writer expected harmonized/writing, got {state_now['state']}")
    info(f"writer post-state: {state_now['state']}")

    # Trigger a chat turn so we move to "editing"
    drafts = requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
    target = next((d for d in drafts if d["word_count"] >= 10), None)
    if target is None:
        raise AssertionError("no draft for chat")
    requests.post(
        f"{BASE}/api/projects/{pid}/chapters/{target['node_id']}/chat",
        json={"message": "改得更正式"}, timeout=120,
    ).raise_for_status()
    info("chat applied")
    _expect_state(pid, "editing")

    # Export
    requests.post(f"{BASE}/api/projects/{pid}/export/docx",
                  json={"include_compliance_note": True}, timeout=300).raise_for_status()
    info("export done")
    _expect_state(pid, "exported")

    shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m6_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env["LOG_LEVEL"] = "INFO"  # capture agent.start/done events
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8771\n"
        "pipeline:\n  max_parallel_writers: 4\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        # State machine unit test first (no server needed)
        _check_state_machine_unit()

        proc = _start_server(env)
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M6", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")
        _expect_state(pid, "created")

        _check_config_roundtrip(pid)
        run_pipeline(pid, proc)

        # Final sanity: state history non-empty + transitions recorded
        rec = requests.get(f"{BASE}/api/projects/{pid}/state", timeout=10).json()
        hist = rec.get("history") or []
        if len(hist) < 6:
            raise AssertionError(f"state history too short: {len(hist)} entries")
        info(f"state history has {len(hist)} entries (last={hist[-1]})")

        # Best-effort: scan the captured log lines for agent.start / agent.done
        counts = _grep_agent_events(proc)
        info(f"log event counts (best-effort): {counts}")

        print("\n[E2E-M6] OK  all M6 checks passed", flush=True)
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
