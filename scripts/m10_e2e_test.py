"""End-to-end test for M10 (plan-first + reviewer agent).

Drives a project through the full pipeline up to writer (mock), then:

  1. POST /report/plan/<leaf_node_id>   → returns SectionPlan ≥3 points
  2. PATCH /report/plan/<node_id>       → edit one point's text
  3. GET   /report/plan/<node_id>       → confirm edit persisted
  4. POST /report/refine/<node_id>      → draft reflects plan
  5. Run mock writer for whole report   (so reviewer sees real drafts)
  6. Inject a numeric inconsistency     (draft has "12345.6789%" not in any StatBlock)
  7. Inject a broken citation           ("Ref<NONEXISTENT>")
  8. POST /review                       → expect ConsistencyChecker + CitationValidator issues
  9. PATCH /review/issues/<id>          → ignore one issue and verify persistence

All under CSR_WRITER_MOCK=1 + CSR_PLAN_MOCK=1 + CSR_REVIEWER_MOCK=1 — no LLM key needed.
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
BASE = "http://127.0.0.1:8775"

sys.path.insert(0, str(ROOT))
from scripts.m4_e2e_test import make_adae, make_adsl, stop_server  # noqa: E402


def info(msg: str) -> None:
    print(f"[E2E-M10] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8775")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8775",
        "--host", "127.0.0.1", "--log-level", "warning",
    ]
    # NOTE: route uvicorn stdout to DEVNULL — when the pipe fills
    # (~64KB on Windows) the writer dispatches block uvicorn's process
    # and the server stops responding. We don't read it anyway.
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


def _apply_cleansing(pid: str, filename: str, content_path: Path) -> None:
    with content_path.open("rb") as f1:
        requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", (filename, f1, "text/csv")),
        ], timeout=60).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + 240
    entries: list[dict] = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(1.0)
    if not entries:
        raise RuntimeError(f"ingest never completed for {filename}")
    found = [e for e in entries if e["filename"] == filename]
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
    requests.post(f"{BASE}/api/projects/{pid}/cleansing/apply",
                   json={"file_id": fid}, timeout=120).raise_for_status()


def _wait_report(pid: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE}/api/projects/{pid}/report/status", timeout=10)
        s = r.json()
        last = s
        if s.get("current_phase") in ("done", "error"):
            return s
        time.sleep(1.5)
    raise TimeoutError(f"report status never settled (last={last})")


def _find_leaf_with_stat_refs(outline: dict) -> dict | None:
    def _walk(nodes):
        for n in nodes:
            if not n.get("children"):
                yield n
            else:
                yield from _walk(n["children"])
    for n in _walk(outline.get("root_sections") or []):
        if n.get("stat_refs"):
            return n
    # fallback — any leaf
    for n in _walk(outline.get("root_sections") or []):
        return n
    return None


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m10_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_PLAN_MOCK"] = "1"
    env["CSR_REVIEWER_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8775\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start_server(env)
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M10", "principle_id": "ich_e3"},
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

        info("running auto analysis…")
        requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                      json={}, timeout=300).raise_for_status()
        info("building outline…")
        requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                      json={"principle_id": "ich_e3"}, timeout=600).raise_for_status()
        outline = requests.get(f"{BASE}/api/projects/{pid}/outline", timeout=10).json()
        leaf = _find_leaf_with_stat_refs(outline)
        if leaf is None:
            raise AssertionError("no leaf found in outline")
        node_id = leaf["id"]
        info(f"target leaf: {node_id} ({leaf['title']}) stat_refs={leaf.get('stat_refs')}")

        # ---------------------------------------------------------------
        # 1. make_plan
        # ---------------------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/report/plan/{node_id}",
                          json={}, timeout=30)
        r.raise_for_status()
        plan = r.json()
        info(f"plan v{plan['version']} with {len(plan['points'])} points")
        if len(plan["points"]) < 3:
            raise AssertionError(f"expected >=3 plan points, got {len(plan['points'])}")

        # ---------------------------------------------------------------
        # 2. PATCH a point
        # ---------------------------------------------------------------
        new_points = list(plan["points"])
        new_points[0]["text"] = "本节首段强调研究目的，并与既往同类研究做对照。(已编辑)"
        new_points[0]["status"] = "edited"
        r = requests.patch(f"{BASE}/api/projects/{pid}/report/plan/{node_id}",
                            json={"points": new_points,
                                  "notes": "edited via e2e"}, timeout=10)
        r.raise_for_status()
        # 3. GET → verify
        r = requests.get(f"{BASE}/api/projects/{pid}/report/plan/{node_id}", timeout=10)
        reloaded = r.json()
        if "(已编辑)" not in reloaded["points"][0]["text"]:
            raise AssertionError("plan edit did not persist")
        info("plan PATCH persisted")

        # ---------------------------------------------------------------
        # 4. refine_to_draft
        # ---------------------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/report/refine/{node_id}",
                           json={}, timeout=120)
        r.raise_for_status()
        draft = r.json()
        info(f"refine produced {draft['word_count']} words")
        if draft["word_count"] < 30:
            raise AssertionError(f"refine output too small: {draft['word_count']} words")
        # warnings should include plan_vX tag
        if not any(w.startswith("plan_v") for w in (draft.get("warnings") or [])):
            raise AssertionError("draft missing plan_vX warning tag")

        # ---------------------------------------------------------------
        # 5. Mock writer full report (so reviewer has many drafts)
        # ---------------------------------------------------------------
        info("running mock writer for full report…")
        requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                       json={"harmonize": False, "leaf_limit": 8},
                       timeout=10).raise_for_status()
        s = _wait_report(pid, timeout_s=300)
        info(f"writer done: phase={s['current_phase']} leaves_done={s['leaves_done']}")
        if s.get("current_phase") == "error":
            raise AssertionError(f"writer errored: {s.get('error')}")

        # ---------------------------------------------------------------
        # 6+7. Inject inconsistency + broken ref by directly editing draft on disk
        # ---------------------------------------------------------------
        sys.path.insert(0, str(BACKEND))
        from app.config import data_dir
        chapters = data_dir() / "projects" / pid / "chapters"
        # find first non-versioned draft file
        targets = [f for f in chapters.glob("*.json")
                    if "_v" not in f.stem and not f.name.startswith("_")]
        if not targets:
            raise AssertionError("no draft files on disk to inject inconsistencies")
        target = targets[0]
        data = json.loads(target.read_text(encoding="utf-8"))
        # inject a number that won't appear in any stat block
        data["markdown"] = (
            data["markdown"]
            + "\n\n## 注入用于测试\n本节包含数值 12345.6789% 用于一致性测试。\n"
            + "另含一个断引用 [RefNONEXISTENT.P1.Col1.Para1] 用于引用校验。\n"
        )
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        info(f"injected inconsistency + broken ref into {target.name}")

        # ---------------------------------------------------------------
        # 8. POST /review
        # ---------------------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/review",
                           json={"sync": True}, timeout=120)
        r.raise_for_status()
        review = r.json()
        info(f"review created: passed={review['passed']} issues={len(review['issues'])}")
        info(f"checkers: " + ", ".join(
            f"{c['name']}({c['issues_count']}, ok={c['ok']})"
            for c in review["checkers"]))
        # ConsistencyChecker should fire on "12345.6789"
        cons_iss = [i for i in review["issues"]
                     if i["checker"] == "consistency"]
        if not cons_iss:
            raise AssertionError("ConsistencyChecker did not catch injected number")
        info(f"consistency issues: {len(cons_iss)}; first message: "
             f"{cons_iss[0]['message'][:100]}")
        # CitationValidator should fire on RefNONEXISTENT
        cit_iss = [i for i in review["issues"]
                     if i["checker"] == "citation"
                     and "NONEXISTENT" in i["message"]]
        if not cit_iss:
            raise AssertionError("CitationValidator did not catch RefNONEXISTENT")
        info(f"citation issue caught: {cit_iss[0]['message'][:100]}")

        # ---------------------------------------------------------------
        # 9. Ignore one issue
        # ---------------------------------------------------------------
        target_iss = cons_iss[0]
        r = requests.patch(
            f"{BASE}/api/projects/{pid}/review/issues/{target_iss['id']}",
            json={"ignored": True}, timeout=10,
        )
        r.raise_for_status()
        # Reload latest
        latest = requests.get(f"{BASE}/api/projects/{pid}/review", timeout=10).json()
        found = next((i for i in latest["issues"] if i["id"] == target_iss["id"]), None)
        if not found or not found.get("ignored"):
            raise AssertionError("ignore flag did not persist on latest review")
        info(f"ignored flag persisted on issue {target_iss['id']}")

        # History
        hist = requests.get(f"{BASE}/api/projects/{pid}/review/history", timeout=10).json()
        info(f"review history entries: {len(hist)}")

        print("\n[E2E-M10] OK  all checks passed", flush=True)
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
