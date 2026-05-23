"""Generate TS + Python SDKs from the live OpenAPI spec.

Usage::

    # Terminal 1
    cd backend && .venv/Scripts/uvicorn app.server.main:app --port 8766

    # Terminal 2
    python scripts/generate_sdk.py [--ts] [--py] [--url URL]

Both generators are optional. If either CLI is missing we log a
``[skip]`` line and continue — installing them is a developer
responsibility, not a runtime requirement.

Required tools (installed on demand):

* TypeScript:  ``npx -y openapi-typescript-codegen``  (Node 18+)
* Python:      ``pip install openapi-python-client``
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDK_DIR = ROOT / "sdk"
DEFAULT_URL = "http://127.0.0.1:8766/openapi.json"


def _info(msg: str) -> None:
    print(f"[gen-sdk] {msg}", flush=True)


def _skip(msg: str) -> None:
    print(f"[gen-sdk][skip] {msg}", flush=True)


def _generate_ts(url: str) -> bool:
    out_dir = SDK_DIR / "ts"
    npx = shutil.which("npx")
    if npx is None:
        _skip("npx not found on PATH; install Node 18+ for the TS SDK")
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        npx, "-y", "openapi-typescript-codegen",
        "--input", url,
        "--output", str(out_dir),
        "--client", "axios",
        "--useOptions",
        "--useUnionTypes",
    ]
    _info("running TS generator")
    try:
        res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as e:
        _skip(f"TS generator unavailable: {e}")
        return False
    if res.returncode != 0:
        _skip(f"TS gen returned {res.returncode}\nstdout={res.stdout[-200:]}\nstderr={res.stderr[-200:]}")
        return False
    _info(f"TS SDK -> {out_dir}")
    return True


def _generate_py(url: str) -> bool:
    out_dir = SDK_DIR / "py"
    out_dir.mkdir(parents=True, exist_ok=True)
    bin = shutil.which("openapi-python-client")
    if bin is None:
        _skip("openapi-python-client not on PATH; pip install openapi-python-client")
        return False
    cmd = [
        bin, "generate",
        "--url", url,
        "--output-path", str(out_dir),
        "--overwrite",
    ]
    _info("running Python generator")
    try:
        res = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as e:
        _skip(f"Python generator unavailable: {e}")
        return False
    if res.returncode != 0:
        _skip(f"Python gen returned {res.returncode}\nstdout={res.stdout[-200:]}\nstderr={res.stderr[-200:]}")
        return False
    _info(f"Python SDK -> {out_dir}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="OpenAPI JSON URL (default: %(default)s)")
    parser.add_argument("--ts", action="store_true", help="Only generate TS SDK")
    parser.add_argument("--py", action="store_true", help="Only generate Python SDK")
    args = parser.parse_args()
    do_ts = args.ts or not (args.ts or args.py)
    do_py = args.py or not (args.ts or args.py)
    SDK_DIR.mkdir(exist_ok=True)
    ok = True
    if do_ts:
        ok = _generate_ts(args.url) and ok
    if do_py:
        ok = _generate_py(args.url) and ok
    return 0 if ok else 0  # Skips are not failures.


if __name__ == "__main__":
    sys.exit(main())
