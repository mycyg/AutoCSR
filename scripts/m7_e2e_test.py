"""End-to-end test for M7 (Python sandbox executor).

Boots uvicorn on :8772, runs through upload+ingest+cleansing apply to
produce a processed parquet, then exercises:

  1. A legitimate analysis snippet (pandas + matplotlib) — must produce
     stdout AND a non-empty chart.png artifact.
  2. Six malicious snippets — each must be rejected (either AST guard or
     runtime), exit_code != 0 or violations non-empty.
  3. An infinite-loop snippet — wall-clock timeout kicks in within ~35s.
  4. A memory-bomb snippet — psutil monitor (Windows) or RLIMIT_AS (Linux)
     kills the child; result.error == "oom" (or exit_code != 0).

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
BASE = "http://127.0.0.1:8772"


def info(msg: str) -> None:
    print(f"[E2E-M7] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr, flush=True)


sys.path.insert(0, str(ROOT))
import scripts.m4_e2e_test as _m4  # noqa: E402
_m4.BASE = BASE
from scripts.m4_e2e_test import (  # noqa: E402
    make_adsl, stop_server,
)


def _start_server(env: dict) -> subprocess.Popen:
    info("starting uvicorn on :8772")
    args = [
        sys.executable, "-m", "uvicorn",
        "app.server.main:app", "--port", "8772",
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


MALICIOUS = [
    ("import_os", "import os\nos.system('echo pwned')"),
    ("dunder_import", "__import__('os').system('echo pwned')"),
    ("eval_exec", "eval(\"__import__('os').system('echo pwned')\")"),
    ("read_passwd",
     "with open('/etc/passwd') as f:\n    print(f.read())"),
    ("read_sam",
     "with open('C:/Windows/system32/config/SAM','rb') as f:\n    print(f.read(10))"),
    ("import_requests",
     "import requests\nrequests.get('https://example.com')"),
]


def _run(pid: str, code: str, **kw) -> dict:
    body = {"code": code}
    body.update(kw)
    r = requests.post(f"{BASE}/api/projects/{pid}/sandbox/run",
                       json=body, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="autocsr_m7_e2e_"))
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    overlay = BACKEND / "app" / "config" / "settings.yaml"
    saved = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(
        "llm:\n  api_key: ''\n"
        "server:\n  host: 127.0.0.1\n  port: 8772\n",
        encoding="utf-8",
    )

    proc = None
    pid = None
    try:
        proc = _start_server(env)

        r = requests.post(f"{BASE}/api/projects",
                          json={"name": "e2e_M7", "principle_id": "ich_e3"},
                          timeout=10)
        r.raise_for_status()
        pid = r.json()["id"]
        info(f"project id: {pid}")

        # Upload an ADSL CSV and run cleansing apply to get a processed parquet.
        adsl = workdir / "fake_adsl.csv"
        make_adsl(adsl)
        with adsl.open("rb") as f1:
            requests.post(f"{BASE}/api/projects/{pid}/upload", files=[
                ("files", ("fake_adsl.csv", f1, "text/csv")),
            ], timeout=60).raise_for_status()
        requests.post(f"{BASE}/api/projects/{pid}/ingest", timeout=10).raise_for_status()
        deadline = time.time() + 120
        entries = []
        while time.time() < deadline:
            s = requests.get(f"{BASE}/api/projects/{pid}/ingest_status", timeout=5).json()
            if s.get("all_done"):
                entries = s["entries"]
                break
            time.sleep(0.5)
        fid = entries[0]["file_id"]
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
        parquet_path = apply_res["processed_path"]
        info(f"processed parquet: {parquet_path}")

        # 1. Legitimate snippet --------------------------------------------
        good_code = (
            "import pandas as pd\n"
            f"df = pd.read_parquet(r'{parquet_path}')\n"
            "print('rows', len(df))\n"
            "print(df.head().to_markdown())\n"
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "ax = df.head(10).select_dtypes('number').plot(kind='bar')\n"
            "plt.tight_layout()\n"
            "plt.savefig('chart.png')\n"
            "print('saved chart.png')\n"
        )
        res = _run(pid, good_code,
                   additional_data_paths=[parquet_path],
                   timeout=30)
        info(f"good run: exit={res['exit_code']} error={res.get('error')} "
             f"duration={res['duration_ms']}ms artifacts={len(res['artifacts'])}")
        if res["exit_code"] != 0:
            err(f"stdout:\n{res['stdout']}\nstderr:\n{res['stderr']}")
            raise AssertionError(f"legitimate snippet failed: exit={res['exit_code']}")
        if not res["stdout"].strip():
            raise AssertionError("legitimate snippet produced empty stdout")
        chart_files = [a for a in res["artifacts"] if a.endswith("chart.png")]
        if not chart_files:
            raise AssertionError(f"chart.png not produced; artifacts={res['artifacts']}")
        size = Path(chart_files[0]).stat().st_size
        if size < 1024:
            raise AssertionError(f"chart.png too small: {size} bytes")
        info(f"chart.png size {size} bytes — OK")

        # Also verify the download route works
        fname = Path(chart_files[0]).name
        dl = requests.get(
            f"{BASE}/api/projects/{pid}/sandbox/runs/{res['run_id']}/artifacts/{fname}",
            timeout=15,
        )
        if dl.status_code != 200 or len(dl.content) < 1024:
            raise AssertionError(f"artifact download failed: {dl.status_code}")
        info("artifact download OK")

        # 2. Six malicious snippets ----------------------------------------
        for name, code in MALICIOUS:
            res = _run(pid, code, timeout=10, mem_mb=256)
            bad = (res["exit_code"] != 0) or bool(res.get("violations"))
            info(f"malicious[{name}]: exit={res['exit_code']} "
                 f"violations={res.get('violations')[:2]} ok={bad}")
            if not bad:
                raise AssertionError(
                    f"malicious snippet {name!r} was NOT rejected; "
                    f"stdout={res['stdout'][:200]!r}",
                )

        # 3. Infinite loop -------------------------------------------------
        t0 = time.time()
        res = _run(pid, "while True:\n    pass\n", timeout=5, mem_mb=256)
        elapsed = time.time() - t0
        info(f"infinite_loop: elapsed={elapsed:.1f}s exit={res['exit_code']} "
             f"error={res.get('error')}")
        if elapsed > 30:
            raise AssertionError(f"timeout took too long: {elapsed:.1f}s")
        if res.get("error") != "timeout" and res["exit_code"] == 0:
            raise AssertionError(
                f"infinite loop not killed: error={res.get('error')} "
                f"exit={res['exit_code']}",
            )

        # 4. Memory bomb ---------------------------------------------------
        t0 = time.time()
        res = _run(
            pid,
            "x = [0] * (10**9)\nprint(len(x))\n",
            timeout=15, mem_mb=64,
        )
        elapsed = time.time() - t0
        info(f"oom_bomb: elapsed={elapsed:.1f}s exit={res['exit_code']} "
             f"error={res.get('error')}")
        if elapsed > 25:
            raise AssertionError(f"oom took too long: {elapsed:.1f}s")
        if res["exit_code"] == 0:
            raise AssertionError(f"memory bomb completed unexpectedly")
        # error should be oom OR crash (some platforms surface as raw crash)
        if res.get("error") not in ("oom", "crash", "timeout"):
            raise AssertionError(f"unexpected error code: {res.get('error')}")

        # 5. /sandbox/runs lists what we've done ---------------------------
        runs = requests.get(f"{BASE}/api/projects/{pid}/sandbox/runs",
                             timeout=10).json()
        if len(runs) < len(MALICIOUS) + 3:
            raise AssertionError(f"runs list too short: {len(runs)}")
        info(f"sandbox runs: {len(runs)} entries")

        print("\n[E2E-M7] OK  all M7 checks passed", flush=True)
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
