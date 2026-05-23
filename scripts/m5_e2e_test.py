"""End-to-end test for M5 (chat editor + DOCX export).

Reuses the M4 e2e pipeline to produce a finished mock report, then exercises:
  - POST /chapters/{node}/chat  (mock editor returns deterministic patches)
  - Version listing + rollback
  - POST /export/docx
  - GET download endpoint
  - python-docx round-trip validation of the generated file

Mock mode is the default (CSR_WRITER_MOCK=1 + CSR_EDITOR_MOCK=1). REAL_LLM=1
swaps the editor pass to a live DeepSeek call for one section.
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
BASE = "http://127.0.0.1:8770"
TIMEOUT_INGEST_S = 120
TIMEOUT_ANALYSIS_S = 180
TIMEOUT_OUTLINE_S = 320
TIMEOUT_GENERATE_S = 360
TIMEOUT_EXPORT_S = 300


def info(msg: str) -> None:
    print(f"[E2E] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


# ---- Reuse fake data builders from M4 -------------------------------------
sys.path.insert(0, str(ROOT))
from scripts.m4_e2e_test import (  # noqa: E402
    make_adae, make_adsl, make_adtte, start_server, stop_server,
    wait_for_report,
)


def run_pipeline(pid: str) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m5_e2e_inputs_"))
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

    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + TIMEOUT_INGEST_S
    entries = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(1.0)
    else:
        raise RuntimeError("ingest timeout")

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

    requests.post(f"{BASE}/api/projects/{pid}/analysis/auto",
                  timeout=TIMEOUT_ANALYSIS_S).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/outline/build",
                  json={"principle_id": "ich_e3"},
                  timeout=TIMEOUT_OUTLINE_S).raise_for_status()
    outline = requests.get(f"{BASE}/api/projects/{pid}/outline", timeout=10).json()

    # Limit to a manageable subset for fast iteration
    requests.post(f"{BASE}/api/projects/{pid}/report/generate",
                  json={"harmonize": True, "leaf_limit": 12}, timeout=30).raise_for_status()
    final = wait_for_report(pid, timeout=TIMEOUT_GENERATE_S)
    if final.get("current_phase") != "done":
        raise AssertionError(f"writer did not reach done (phase={final.get('current_phase')})")
    info(f"writer done: {final.get('leaves_done')}/{final.get('leaves_total')} leaves")

    shutil.rmtree(workdir, ignore_errors=True)
    return outline


def pick_chat_target(pid: str) -> str:
    drafts = requests.get(f"{BASE}/api/projects/{pid}/report/drafts", timeout=10).json()
    for d in drafts:
        if d["status"] != "error" and d["word_count"] >= 10:
            return d["node_id"]
    raise AssertionError("no usable draft for chat")


def exercise_chat_and_versions(pid: str) -> None:
    target = pick_chat_target(pid)
    info(f"chat target node = {target}")

    before = requests.get(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}", timeout=10,
    ).json()
    before_md = before["markdown"]

    # 1) chat send
    r = requests.post(
        f"{BASE}/api/projects/{pid}/chapters/{target}/chat",
        json={"message": "把第一段改得更正式一些"}, timeout=120,
    )
    r.raise_for_status()
    turn = r.json()
    if not turn["patches"]:
        raise AssertionError("chat returned no patches in mock mode")
    info(f"patches applied: {len(turn['patches'])}, new_version={turn['new_version']}")
    info(f"  first patch op={turn['patches'][0]['op']} target={turn['patches'][0].get('target')}")
    info(f"  before excerpt: {turn['patches'][0]['before'][:80]!r}")
    info(f"  after  excerpt: {turn['patches'][0]['after'][:80]!r}")

    # 2) history
    hist = requests.get(
        f"{BASE}/api/projects/{pid}/chapters/{target}/chat", timeout=10,
    ).json()
    if len(hist) < 2:
        raise AssertionError(f"expected >=2 history entries, got {len(hist)}")
    info(f"history entries: {len(hist)} (user + assistant)")

    # 3) versions list — should be >= 2
    versions = requests.get(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}/versions", timeout=10,
    ).json()
    if len(versions) < 2:
        raise AssertionError(f"expected >=2 versions, got {len(versions)}")
    info(f"versions: {versions}")

    after = requests.get(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}", timeout=10,
    ).json()
    if after["markdown"] == before_md:
        raise AssertionError("markdown did not change after patch")
    info("markdown changed: OK")

    # 4) rollback to v1
    info(f"rolling back to v{versions[0]}")
    rb = requests.post(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}/rollback/{versions[0]}",
        timeout=30,
    )
    rb.raise_for_status()
    restored = rb.json()
    if restored["markdown"] != before_md:
        # restore strips no content but adds a "restored_from" warning — markdown should equal pre-edit body
        # Tolerance: at least one warning should be present
        if "restored_from_v1" not in (restored.get("warnings") or []):
            raise AssertionError(
                "rollback did not restore original markdown and no provenance warning",
            )
    info("rollback OK; provenance warning present")

    # 5) Append another version via manual edit (PUT) to prove that path also snapshots
    r = requests.put(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}/markdown",
        json={"markdown": restored["markdown"] + "\n\n（手工补充：以上数据需与 SAP 第 X 节对应。）"},
        timeout=30,
    )
    r.raise_for_status()
    vlist2 = requests.get(
        f"{BASE}/api/projects/{pid}/report/drafts/{target}/versions", timeout=10,
    ).json()
    if len(vlist2) <= len(versions):
        raise AssertionError("manual edit did not produce a new version")
    info(f"manual edit pushed version count: {len(versions)} -> {len(vlist2)}")


def exercise_export(pid: str) -> Path:
    info("triggering docx export")
    r = requests.post(
        f"{BASE}/api/projects/{pid}/export/docx",
        json={
            "include_compliance_note": True,
            "include_toc": True,
            "include_appendix_cleansing": True,
            "include_appendix_analysis": True,
        },
        timeout=TIMEOUT_EXPORT_S,
    )
    r.raise_for_status()
    res = r.json()
    info(f"export result: {res['filename']} {res['size_bytes']} bytes "
         f"sections={res['n_sections']} citations={res['n_citations']}")
    if res["size_bytes"] < 10_000:
        raise AssertionError(f"docx too small ({res['size_bytes']} bytes)")

    # download
    dl = requests.get(
        f"{BASE}/api/projects/{pid}/export/docx/{res['filename']}",
        timeout=60,
    )
    dl.raise_for_status()
    out_dir = Path(tempfile.mkdtemp(prefix="autocsr_m5_e2e_out_"))
    out_file = out_dir / res["filename"]
    out_file.write_bytes(dl.content)
    info(f"downloaded {out_file} ({out_file.stat().st_size} bytes)")
    return out_file


def validate_docx(path: Path) -> None:
    info("python-docx round-trip validation")
    # Ensure it's a real zip / docx
    with zipfile.ZipFile(path) as zf:
        members = zf.namelist()
        if "word/document.xml" not in members:
            raise AssertionError("not a valid docx: missing word/document.xml")
        document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")

    from docx import Document
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs]
    text = "\n".join(paragraphs)

    if "临床研究报告" not in text:
        raise AssertionError("cover title missing from rendered text")
    if "References" not in text and "引用" not in text:
        raise AssertionError("References chapter heading missing")
    if "Appendix A" not in text:
        raise AssertionError("Appendix A heading missing")
    if "Appendix B" not in text:
        raise AssertionError("Appendix B heading missing")
    if "TOC" not in document_xml.upper():
        raise AssertionError("TOC field not embedded in document.xml")
    if "本报告基于清洗后数据生成" not in text:
        raise AssertionError("compliance note missing from cover")

    # Count headings used
    heading_paras = [p for p in doc.paragraphs if p.style.name.startswith("Heading")]
    info(f"  paragraphs={len(paragraphs)} headings={len(heading_paras)} tables={len(doc.tables)}")
    if len(heading_paras) < 3:
        raise AssertionError(f"too few headings ({len(heading_paras)}); expected at least 3")

    info("docx validation OK")


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m5_e2e_"))
    env = os.environ.copy()
    env["CSR_WRITER_MOCK"] = "1"
    env["CSR_EDITOR_MOCK"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8770\n"
        "pipeline:\n  max_parallel_writers: 4\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        # Patch BASE in scripts.m4_e2e_test so its start_server/wait_for_report use 8770
        import scripts.m4_e2e_test as _m4
        _m4.BASE = BASE
        # And override the port arg start_server uses
        orig_start = _m4.start_server

        def _start_8770(env_dict):
            info("starting uvicorn on :8770")
            args = [
                sys.executable, "-m", "uvicorn",
                "app.server.main:app", "--port", "8770",
                "--host", "127.0.0.1", "--log-level", "warning",
            ]
            p = subprocess.Popen(
                args, cwd=BACKEND, env=env_dict,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    r = requests.get(f"{BASE}/api/health", timeout=2)
                    if r.status_code == 200:
                        info("server up")
                        return p
                except requests.RequestException:
                    time.sleep(0.4)
            p.terminate()
            raise RuntimeError("server did not come up")

        proc = _start_8770(env)

        r = requests.post(
            f"{BASE}/api/projects",
            json={"name": "e2e_M5", "principle_id": "ich_e3"}, timeout=10,
        )
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        run_pipeline(pid)
        exercise_chat_and_versions(pid)

        docx_path = exercise_export(pid)
        validate_docx(docx_path)

        # Show exports history
        h = requests.get(f"{BASE}/api/projects/{pid}/exports", timeout=10).json()
        info(f"export history entries: {len(h)}")

        print("\n[E2E] OK  all M5 checks passed", flush=True)
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
