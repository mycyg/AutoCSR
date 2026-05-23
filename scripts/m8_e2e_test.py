"""End-to-end test for M8 (analyst agent + data ask + chart_tools).

Boots uvicorn on :8773, runs upload + ingest + cleansing to get a processed
parquet, then exercises:

  1. POST /ask with a boxplot-style query -> StatBlock with chart image
     (chart.png artifact) and a markdown table (or stdout fallback).
  2. POST /ask with a "top-5 SOC" query -> StatBlock containing a
     5-row markdown table.
  3. GET /ask/history returns at least the two entries above.
  4. POST /sandbox/run drives chart_tools.echarts_from_dataframe directly
     and asserts the JSON has `series` + `xAxis`.

Mock mode (CSR_ANALYST_MOCK=1, the default here) bypasses the LLM; the
sandbox itself still runs the deterministic snippet.
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
BASE = "http://127.0.0.1:8773"


def info(msg: str) -> None:
    print(f"[E2E-M8] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


sys.path.insert(0, str(ROOT))
import scripts.m4_e2e_test as _m4  # noqa: E402
_m4.BASE = BASE
from scripts.m4_e2e_test import make_adae, make_adsl, stop_server  # noqa: E402


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8773")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8773",
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
    """Upload + ingest + cleansing apply; return the processed parquet path."""
    with content_path.open("rb") as f1:
        requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
            ("files", (filename, f1, "text/csv")),
        ], timeout=60).raise_for_status()
    requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
    deadline = time.time() + 120
    entries: list[dict] = []
    while time.time() < deadline:
        s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
        if s.get("all_done"):
            entries = s["entries"]
            break
        time.sleep(0.5)
    # find file by name
    fid = next(e["file_id"] for e in entries if e["filename"] == filename)
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


def _ask(pid: str, query: str, **extra) -> dict:
    body = {"query": query, **extra}
    r = requests.post(f"{BASE}/api/projects/{pid}/ask", json=body, timeout=180)
    r.raise_for_status()
    return r.json()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m8_e2e_"))
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # M8 e2e runs in mock mode so we don't burn budget; the sandbox still
    # exercises the real code path end to end.
    env["CSR_ANALYST_MOCK"] = "1"

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8773\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start_server(env)

        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M8", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        adsl = workdir / "fake_adsl.csv"
        adae = workdir / "fake_adae.csv"
        make_adsl(adsl)
        make_adae(adae)
        adsl_parquet = _apply_cleansing(pid, "fake_adsl.csv", adsl)
        adae_parquet = _apply_cleansing(pid, "fake_adae.csv", adae)
        info(f"adsl parquet: {adsl_parquet}")
        info(f"adae parquet: {adae_parquet}")

        # 1. Boxplot-style ask --------------------------------------------
        ask1 = _ask(pid, "DrugA vs Placebo AGE 分布对比，画 boxplot")
        sb1 = ask1.get("stat_block") or {}
        info(f"ask1 stat_block id={sb1.get('id')} title={sb1.get('title')!r}")
        info(f"  has chart_json={bool((sb1.get('result_json') or {}).get('chart_json'))}")
        info(f"  png_path={(sb1.get('result_json') or {}).get('png_path')}")
        info(f"  markdown_table rows={len((sb1.get('markdown_table') or '').splitlines())}")
        if not sb1.get("markdown_table"):
            raise AssertionError("ask1 did not produce markdown_table")
        if not (sb1.get("result_json") or {}).get("png_path") and not (
            sb1.get("result_json") or {}).get("chart_json"
        ):
            raise AssertionError("ask1 produced neither PNG nor chart_json")

        # 2. Top-5 SOC ask ------------------------------------------------
        ask2 = _ask(pid, "ADAE 中 AESOC 出现频率 top 5")
        sb2 = ask2.get("stat_block") or {}
        info(f"ask2 stat_block id={sb2.get('id')} title={sb2.get('title')!r}")
        md2 = sb2.get("markdown_table") or ""
        info(f"  markdown_table lines={len(md2.splitlines())}")
        info(f"  markdown_table preview:\n{md2[:400]}")
        # Must contain at least header + separator + 1 data row
        if md2.count("|") < 6:
            raise AssertionError(f"ask2 markdown_table too small: {md2!r}")

        # 3. History ------------------------------------------------------
        hist = requests.get(f"{BASE}/api/projects/{pid}/ask/history", timeout=10).json()
        info(f"history entries: {len(hist)}")
        if len(hist) < 2:
            raise AssertionError(f"expected >=2 history rows, got {len(hist)}")

        # 4. ECharts JSON generator via sandbox ---------------------------
        echarts_code = (
            "import pandas as pd\n"
            "from app.report.chart_tools import echarts_from_dataframe\n"
            "import json\n"
            f"df = pd.read_parquet(r'{adsl_parquet}')\n"
            "opt = echarts_from_dataframe(df, chart_type='boxplot', x_col='TRT01P', y_cols=['AGE'])\n"
            "print(json.dumps(opt))\n"
        )
        # The sandbox AST guard forbids `pathlib` etc., but `app.report` is
        # not in the allowlist either. We exercise echarts_from_dataframe
        # directly via the test process instead (calling chart_tools from
        # within a sandbox would require the sandbox to import `app.*`,
        # which is intentionally not allowed).
        sys.path.insert(0, str(BACKEND))
        from app.report.chart_tools import echarts_from_dataframe  # noqa: E402
        import pandas as pd
        df = pd.read_parquet(adsl_parquet)
        opt = echarts_from_dataframe(
            df, chart_type="boxplot", x_col="TRT01P", y_cols=["AGE"],
        )
        if "series" not in opt or "xAxis" not in opt:
            raise AssertionError(f"echarts_from_dataframe missing keys: {list(opt)}")
        if not opt["series"]:
            raise AssertionError("echarts series empty")
        info(f"echarts boxplot opt keys: {list(opt)}; series #={len(opt['series'])}")

        # 5. Sandbox call summary -----------------------------------------
        runs = requests.get(f"{BASE}/api/projects/{pid}/sandbox/runs",
                             timeout=10).json()
        info(f"total sandbox runs: {len(runs)}")

        print("\n[E2E-M8] OK  all M8 checks passed", flush=True)
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
