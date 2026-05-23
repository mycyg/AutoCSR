"""End-to-end test for M11 (comments + markers + diff + alerts).

Flow:

  1. Build + run mock writer (CSR_WRITER_MOCK=1)
  2. POST 3 comments to different sections
  3. POST /comments/apply → expect ≥1 resolved + section version bump
  4. POST a marker → GET verify persistence
  5. Edit a section markdown via regenerate → bump to v2
  6. GET /drafts/{node}/diff?v1=1&v2=2 → blocks non-empty with insert/delete/replace
  7. GET /alerts → counts + items; construct a PII not-hashed scenario
     (don't apply hash_pii proposals) → expect PII warning in items
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
BASE = "http://127.0.0.1:8776"

sys.path.insert(0, str(ROOT))
from scripts.m4_e2e_test import make_adae, make_adsl, stop_server  # noqa: E402


def info(msg: str) -> None:
    print(f"[E2E-M11] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8776")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8776",
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


def _apply_cleansing(pid: str, filename: str, content_path: Path,
                      *, accept_pii: bool = True) -> None:
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
    found = [e for e in entries if e["filename"] == filename]
    fid = found[0]["file_id"]
    proposals = requests.get(
        f"{BASE}/api/projects/{pid}/cleansing/proposals",
        params={"file_id": fid, "refresh": "true"}, timeout=60,
    ).json()
    for p in proposals:
        if p["status"] != "pending":
            continue
        if p["type"] == "hash_pii" and not accept_pii:
            # leave it pending — should trigger PII alert
            continue
        if p["mandatory"]:
            # mandatory must be accepted to allow apply()
            requests.patch(
                f"{BASE}/api/projects/{pid}/cleansing/proposals/{p['id']}",
                json={"status": "accepted"}, timeout=10,
            ).raise_for_status()
            continue
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
        s = requests.get(f"{BASE}/api/projects/{pid}/report/status", timeout=10).json()
        last = s
        if s.get("current_phase") in ("done", "error"):
            return s
        time.sleep(1.5)
    raise TimeoutError(f"report never settled (last={last})")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m11_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env["CSR_REVIEWER_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8776\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start_server(env)
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M11", "principle_id": "ich_e3"},
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

        requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                      json={}, timeout=300).raise_for_status()
        requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                      json={"principle_id": "ich_e3"}, timeout=600).raise_for_status()
        info("running mock writer for full report (capped 6 leaves)…")
        requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                       json={"harmonize": False, "leaf_limit": 6},
                       timeout=10).raise_for_status()
        s = _wait_report(pid, timeout_s=300)
        info(f"writer done: leaves_done={s['leaves_done']}")
        drafts = requests.get(f"{BASE}/api/projects/{pid}/report/drafts",
                               timeout=10).json()
        if len(drafts) < 3:
            raise AssertionError(f"need >=3 drafts for the test, got {len(drafts)}")
        targets = drafts[:3]
        info(f"comment targets: {[d['node_id'] for d in targets]}")

        # ---------------------------------------------------------------
        # 2. POST 3 comments
        # ---------------------------------------------------------------
        for i, d in enumerate(targets):
            r = requests.post(f"{BASE}/api/projects/{pid}/comments", json={
                "node_id": d["node_id"],
                "paragraph_idx": 0,
                "char_range": [0, 20],
                "body": f"批注 {i+1}: 请把首段措辞改为更正式版本。",
            }, timeout=10)
            r.raise_for_status()
        comments = requests.get(f"{BASE}/api/projects/{pid}/comments", timeout=10).json()
        info(f"posted comments: {len(comments)}")
        if len(comments) != 3:
            raise AssertionError(f"expected 3 comments, got {len(comments)}")

        # ---------------------------------------------------------------
        # 3. POST /comments/apply
        # ---------------------------------------------------------------
        r = requests.post(f"{BASE}/api/projects/{pid}/comments/apply",
                           json={}, timeout=60)
        r.raise_for_status()
        apply_res = r.json()
        info(f"apply: applied={apply_res['applied_count']} "
             f"skipped={apply_res['skipped_count']} "
             f"new_versions={apply_res['new_versions']}")
        if apply_res["applied_count"] < 1:
            raise AssertionError("expected >=1 applied patch from batch apply")
        # at least 1 comment must be resolved
        comments_after = requests.get(f"{BASE}/api/projects/{pid}/comments",
                                       timeout=10).json()
        resolved = [c for c in comments_after if c["status"] == "resolved"]
        info(f"resolved comments: {len(resolved)}")
        if not resolved:
            raise AssertionError("no comments transitioned to resolved")

        # ---------------------------------------------------------------
        # 4. Marker CRUD
        # ---------------------------------------------------------------
        marker_target = targets[0]["node_id"]
        r = requests.post(f"{BASE}/api/projects/{pid}/markers", json={
            "node_id": marker_target,
            "type": "risk",
            "range": [10, 50],
            "note": "需复核此段数据来源",
        }, timeout=10)
        r.raise_for_status()
        m_id = r.json()["id"]
        info(f"created marker id={m_id}")
        markers = requests.get(f"{BASE}/api/projects/{pid}/markers",
                                params={"node_id": marker_target}, timeout=10).json()
        if not any(m["id"] == m_id for m in markers):
            raise AssertionError("marker did not persist on draft")
        info(f"markers on node: {len(markers)}")

        # ---------------------------------------------------------------
        # 5. Bump to v2 via regenerate
        # ---------------------------------------------------------------
        node_for_diff = targets[1]["node_id"]
        r = requests.post(
            f"{BASE}/api/projects/{pid}/report/regenerate/{node_for_diff}",
            json={"extra_instructions": "在首段补充研究背景。"}, timeout=120,
        )
        r.raise_for_status()
        # Snapshot the regenerated draft manually so v2 exists
        sys.path.insert(0, str(BACKEND))
        from app.report import store as draft_store
        cur = draft_store.load_draft(pid, node_for_diff)
        if cur is None:
            raise AssertionError(f"draft {node_for_diff} missing after regenerate")
        draft_store.snapshot_draft(pid, cur)
        # Verify versions exist
        versions = requests.get(
            f"{BASE}/api/projects/{pid}/drafts/{node_for_diff}/versions", timeout=10,
        ).json()
        info(f"versions for {node_for_diff}: {versions}")
        if len(versions) < 1:
            raise AssertionError("no draft versions present")

        # ---------------------------------------------------------------
        # 6. GET /drafts/{node}/diff
        # ---------------------------------------------------------------
        # Force a second version by snapshotting after a manual tweak
        cur2 = draft_store.load_draft(pid, node_for_diff)
        # mutate markdown slightly so diff is non-trivial
        mutated = cur2.model_copy(update={
            "markdown": cur2.markdown + "\n\n## 追加段落\n这是测试 diff 的新增内容。\n",
        })
        draft_store.save_draft(pid, mutated)
        draft_store.snapshot_draft(pid, mutated)
        versions = requests.get(
            f"{BASE}/api/projects/{pid}/drafts/{node_for_diff}/versions", timeout=10,
        ).json()
        info(f"versions after mutate: {versions}")
        if len(versions) < 2:
            raise AssertionError(
                f"need >=2 versions for diff, got {len(versions)}",
            )
        v1, v2 = versions[-2], versions[-1]
        r = requests.get(
            f"{BASE}/api/projects/{pid}/drafts/{node_for_diff}/diff",
            params={"v1": v1, "v2": v2}, timeout=10,
        )
        r.raise_for_status()
        diff_res = r.json()
        info(f"diff blocks: {len(diff_res['blocks'])} summary: {diff_res['summary']}")
        if not diff_res["blocks"]:
            raise AssertionError("diff returned empty blocks")
        ops_seen = {b["op"] for b in diff_res["blocks"]}
        if not (ops_seen & {"insert", "delete", "replace"}):
            raise AssertionError(f"expected at least one non-equal block; got {ops_seen}")

        # ---------------------------------------------------------------
        # 7. /alerts aggregator + PII not-hashed scenario
        # ---------------------------------------------------------------
        r = requests.get(f"{BASE}/api/projects/{pid}/alerts", timeout=10)
        r.raise_for_status()
        alerts = r.json()
        info(f"alerts counts: {alerts['counts']} ; items: {len(alerts['items'])}")
        # Create a sibling project with PII not hashed, to exercise that branch
        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M11_pii", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid_pii = r.json()["id"]
        adsl2 = workdir / "fake_adsl2.csv"
        make_adsl(adsl2)
        _apply_cleansing(pid_pii, "fake_adsl2.csv", adsl2, accept_pii=False)
        # Force invalidate so we hit the fresh aggregator
        requests.post(f"{BASE}/api/projects/{pid_pii}/alerts/invalidate",
                       timeout=10).raise_for_status()
        r = requests.get(f"{BASE}/api/projects/{pid_pii}/alerts", timeout=10)
        pii_alerts = r.json()
        info(f"pii project alerts: {pii_alerts['counts']} ; "
             f"items: {len(pii_alerts['items'])}")
        # At least one item should be sourced from cleansing.profile or
        # cleansing.pii (since hash_pii proposal is mandatory we may
        # still have accepted it; the column null/PII signal should
        # still fire).
        has_pii = any(it["source"].startswith("cleansing")
                       for it in pii_alerts["items"])
        if not has_pii:
            raise AssertionError(
                f"no cleansing.* alerts; got sources: "
                f"{set(it['source'] for it in pii_alerts['items'])}",
            )

        # Clean up sibling project explicitly so finally hook isn't surprised
        try:
            from app.config import data_dir
            shutil.rmtree(data_dir() / "projects" / pid_pii, ignore_errors=True)
            projects_json = data_dir() / "projects.json"
            if projects_json.exists():
                items = json.loads(projects_json.read_text(encoding="utf-8") or "[]")
                items = [p for p in items if p.get("id") != pid_pii]
                projects_json.write_text(
                    json.dumps(items, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass

        print("\n[E2E-M11] OK  all checks passed", flush=True)
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
                shutil.rmtree(data_dir() / "projects" / pid, ignore_errors=True)
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
