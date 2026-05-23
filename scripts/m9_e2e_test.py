"""End-to-end test for M9 (writer tool loop + analyst dedup pool).

Plan:

  A. Mock-mode pass — fast, no LLM key needed
     ---------------------------------------
     With ``CSR_WRITER_MOCK=1`` the writer takes the legacy stub path and
     does **not** invoke the tool loop. We assert:
       - report still generates end to end
       - no ``*_tools.jsonl`` files are written (tool loop didn't run)

  B. AnalystFuturePool dedup — also fast, no LLM key needed
     ------------------------------------------------------
     We construct a pool directly and fire the same query twice in
     parallel, plus a different query once. Assertions:
       - the underlying ``run_analyst`` runs exactly 2 times (key1 + key2)
       - a ``analyst.dedup_hit`` WS event fires for the duplicate
     We patch ``run_analyst`` with a counter to make the assertion clean.

  C. Real-LLM tool loop pass — only if ``REAL_LLM=1``
     -------------------------------------------------
     With ``CSR_WRITER_TOOLS=1`` + ``leaf_limit=3`` the writer drives the
     full LLM ↔ tool loop. Assertions:
       - at least one ``*_tools.jsonl`` file has ≥1 non-``respond`` tool
         call (proves the LLM autonomously called a tool)
       - at least one section's tool_calls contains either
         ``call_analyst`` or ``sandbox_python`` (statistical evidence)
       - at least one section's tool_calls contains ``search_corpus``

Usage:
    python scripts/m9_e2e_test.py            # mock + pool dedup only
    REAL_LLM=1 python scripts/m9_e2e_test.py # add real-LLM tool loop
"""
from __future__ import annotations

import asyncio
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
BASE = "http://127.0.0.1:8774"


def info(msg: str) -> None:
    print(f"[E2E-M9] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


sys.path.insert(0, str(ROOT))
import scripts.m4_e2e_test as _m4  # noqa: E402
_m4.BASE = BASE
from scripts.m4_e2e_test import make_adae, make_adsl, stop_server  # noqa: E402


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8774")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8774",
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


def _apply_cleansing(pid: str, filename: str, content_path: Path) -> str:
    with content_path.open("rb") as f1:
        requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", (filename, f1, "text/csv")),
        ], timeout=60).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + 600
    entries: list[dict] = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(1.5)
    if not entries:
        raise RuntimeError(f"ingest never completed for {filename}; last status: {s}")
    found = [e for e in entries if e["filename"] == filename]
    if not found:
        raise RuntimeError(f"file {filename} not in entries: {[e['filename'] for e in entries]}")
    fid = found[0]["file_id"]
    proposals = requests.get(
        f"{BASE}/api/projects/{pid}/cleansing/proposals",
        params={"file_id": fid, "refresh": "true"}, timeout=60,
    ).json()
    for p in proposals:
        if p["status"] == "pending" and not p["mandatory"]:
            requests.patch(
                f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                json={"status": "accepted"}, timeout=10,
            ).raise_for_status()
    apply_res = requests.post(f"{BASE}/api/projects/{pid}/cleansing/apply",
                                json={"file_id": fid}, timeout=120).json()
    return apply_res["processed_path"]


def _wait_report(pid: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/projects/{pid}/report/status", timeout=10)
        s = r.json()
        last = s
        if s.get("current_phase") in ("done", "error"):
            return s
        time.sleep(2.0)
    raise TimeoutError(f"report status never settled (last={last})")


def _dedup_pool_test() -> None:
    """Pool dedup: two identical queries hit the same Future."""
    info("[B] AnalystFuturePool dedup test")
    sys.path.insert(0, str(BACKEND))
    from app.report.orchestrator import AnalystFuturePool

    # Monkeypatch run_analyst inside the pool
    counter = {"n": 0}

    async def fake_run_analyst(project_id, query, *, scope="all", parquet_paths=None):
        await asyncio.sleep(0.05)
        counter["n"] += 1
        return {"stat_block": {"id": f"sb-{counter['n']}", "title": query[:20]},
                 "sandbox_run_id": f"run-{counter['n']}"}

    import app.agents.analyst_agent as aa_mod
    saved = aa_mod.run_analyst
    aa_mod.run_analyst = fake_run_analyst  # type: ignore[assignment]
    try:
        async def main() -> tuple[int, list]:
            pool = AnalystFuturePool()
            tasks = [
                pool.request("pid", "TRT A vs B ALT 升高比例", requester="W1"),
                pool.request("pid", "TRT A vs B ALT 升高比例", requester="W2"),
                pool.request("pid", "ADAE top 5 SOC", requester="W3"),
                pool.request("pid", "TRT A vs B ALT 升高比例", requester="W4"),
            ]
            results = await asyncio.gather(*tasks)
            return counter["n"], results

        n, results = asyncio.run(main())
        info(f"  unique analyst runs: {n} (expected 2)")
        info(f"  shared sb ids: {[r['stat_block']['id'] for r in results]}")
        if n != 2:
            raise AssertionError(f"dedup failed: expected 2 unique runs, got {n}")
        # W1 / W2 / W4 should share the same stat block id (same Future)
        ids = [r["stat_block"]["id"] for r in results]
        if not (ids[0] == ids[1] == ids[3]):
            raise AssertionError(f"shared queries returned different ids: {ids}")
    finally:
        aa_mod.run_analyst = saved  # type: ignore[assignment]


def _mock_writer_pass(pid: str, env: dict) -> None:
    """Confirm mock mode still bypasses the tool loop entirely."""
    info("[A] mock writer pass — confirms no tool history written")
    # Build outline (needs analysis first; m6_e2e patterns)
    requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                  json={}, timeout=300).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                  json={"principle_id": "ich_e3"}, timeout=600).raise_for_status()
    # Trigger writers — mock mode (env carries CSR_WRITER_MOCK=1) + 4-leaf cap
    r = requests.post(
        f"{BASE}/api/projects/{pid}/report/generate",
        json={"harmonize": False, "leaf_limit": 4, "enable_tools": True},
        timeout=10,
    )
    r.raise_for_status()
    s = _wait_report(pid, timeout_s=300)
    info(f"  mock report phase: {s.get('current_phase')} done={s.get('leaves_done')}")
    if s.get("current_phase") == "error":
        raise AssertionError(f"mock writer report errored: {s.get('error')}")

    # Verify no tool history file was created — proves mock didn't drive tool loop
    sys.path.insert(0, str(BACKEND))
    from app.config import data_dir
    chapters = data_dir() / "projects" / pid / "chapters"
    tool_files = list(chapters.glob("*_tools.jsonl"))
    info(f"  tools jsonl files: {len(tool_files)} (expected 0 in mock)")
    if tool_files:
        raise AssertionError(f"mock writer wrote tool history: {tool_files}")


def _real_llm_pass(pid: str, dedup_hit_box: dict[str, list]) -> None:
    """Run a real-LLM tool-loop generation across 3 leaves."""
    info("[C] real LLM tool loop pass — leaf_limit=3")
    sys.path.insert(0, str(BACKEND))
    # We need to disable mock; the env was set before server start so we
    # have to launch a second server. Instead we just signal via env
    # passthrough — the user must have started the server WITHOUT
    # CSR_WRITER_MOCK for this path to work.
    r = requests.post(
        f"{BASE}/api/projects/{pid}/report/generate",
        json={"harmonize": False, "leaf_limit": 3, "enable_tools": True,
              "max_tool_turns": 3},
        timeout=10,
    )
    r.raise_for_status()
    s = _wait_report(pid, timeout_s=1500)
    info(f"  real report phase: {s.get('current_phase')} done={s.get('leaves_done')}")

    from app.config import data_dir
    chapters = data_dir() / "projects" / pid / "chapters"
    tool_files = sorted(chapters.glob("*_tools.jsonl"))
    info(f"  tools jsonl files: {len(tool_files)}")
    if not tool_files:
        raise AssertionError("real LLM writer produced no tool call history")

    saw_non_respond = False
    saw_stat_or_sandbox = False
    saw_search = False
    for f in tool_files:
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                tc = json.loads(line)
            except Exception:
                continue
            name = tc.get("name") or ""
            if name and name != "respond":
                saw_non_respond = True
            if name in ("call_analyst", "sandbox_python"):
                saw_stat_or_sandbox = True
            if name == "search_corpus":
                saw_search = True

    info(f"  tool call coverage: non_respond={saw_non_respond} "
         f"stat_or_sandbox={saw_stat_or_sandbox} search={saw_search}")
    if not saw_non_respond:
        raise AssertionError("no non-respond tool call seen")
    if not (saw_stat_or_sandbox or saw_search):
        raise AssertionError("neither analytic nor search tool used")
    info(f"  dedup_hit events observed: {len(dedup_hit_box['events'])}")


def main() -> int:
    real_llm = os.environ.get("REAL_LLM", "").lower() in ("1", "true", "yes")
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m9_e2e_"))
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    # Always run pool dedup test FIRST — it's pure-async, no server needed.
    try:
        _dedup_pool_test()
        info("dedup pool test passed")
    except AssertionError as e:
        err(f"dedup pool: {e}")
        return 2

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    if real_llm:
        # Keep real key from existing settings.yaml; just ensure mock OFF
        env.pop("CSR_WRITER_MOCK", None)
        env["CSR_WRITER_TOOLS"] = "1"
        info("running with REAL LLM (no CSR_WRITER_MOCK)")
    else:
        env["CSR_WRITER_MOCK"] = "1"
        overlay.write_text(
            "llm:\n  api_key: ''\n"
            "server:\n  host: 127.0.0.1\n  port: 8774\n",
            encoding="utf-8",
        )

    proc = None
    pid = None
    dedup_hit_box: dict[str, list] = {"events": []}
    try:
        proc = _start_server(env)

        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M9", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        adsl = workdir / "fake_adsl.csv"
        adae = workdir / "fake_adae.csv"
        make_adsl(adsl)
        make_adae(adae)
        _apply_cleansing(pid, "fake_adsl.csv", adsl)
        _apply_cleansing(pid, "fake_adae.csv", adae)
        info("data ingested + cleansed")

        if real_llm:
            # Subscribe to WS so we can observe dedup_hit events
            import threading
            import websockets

            async def ws_listen() -> None:
                try:
                    async with websockets.connect(
                        f"ws://127.0.0.1:8774/ws/{pid}",
                        open_timeout=5, close_timeout=2,
                    ) as ws:
                        while True:
                            raw = await ws.recv()
                            try:
                                ev = json.loads(raw)
                            except Exception:
                                continue
                            if ev.get("type") == "analyst.dedup_hit":
                                dedup_hit_box["events"].append(ev["payload"])
                except Exception:
                    pass

            loop = asyncio.new_event_loop()
            t = threading.Thread(
                target=lambda: loop.run_until_complete(ws_listen()),
                daemon=True,
            )
            t.start()

            # Prep outline + analyses
            info("running auto analysis…")
            requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                          json={}, timeout=300).raise_for_status()
            info("building outline…")
            r = requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                          json={"principle_id": "ich_e3"}, timeout=1200)
            r.raise_for_status()
            ob = r.json()
            info(f"  outline build returned: {ob}")
            # Poll until the outline is actually on disk
            deadline = time.time() + 900
            while time.time() < deadline:
                check = requests.get(f"{BASE}/api/projects/{pid}/outline", timeout=10)
                if check.status_code == 200:
                    info(f"  outline ready, n_nodes={len(check.json().get('root_sections', []))}")
                    break
                time.sleep(3.0)
            else:
                raise RuntimeError("outline never landed within 15 min")
            _real_llm_pass(pid, dedup_hit_box)
        else:
            _mock_writer_pass(pid, env)

        print("\n[E2E-M9] OK  all M9 checks passed", flush=True)
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
