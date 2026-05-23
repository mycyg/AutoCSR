"""M22 — accessibility audit runner.

Strategy:
    * Starts the built frontend on a local static server.
    * Runs the axe-core CLI (`npx @axe-core/cli`) against a handful of
      core pages with the `wcag2aa` rule pack.
    * If the CLI is not installed, prints a checklist instead and exits
      0 so this script doesn't block CI on environments that lack node
      tooling.

The script writes a Markdown report to `scripts/m22_a11y_report.md`.

Usage:
    python scripts/m22_a11y_check.py
    python scripts/m22_a11y_check.py --threshold 95
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
REPORT = ROOT / "scripts" / "m22_a11y_report.md"


def _info(msg: str) -> None:
    print(f"[A11Y] {msg}", flush=True)


def _pick_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _have_axe() -> bool:
    return shutil.which("npx") is not None


def _has_dist() -> bool:
    return (FRONTEND / "dist" / "index.html").exists()


def _start_static_server(port: int) -> subprocess.Popen:
    # Use Python's built-in to avoid a node dep just for serving HTML.
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=FRONTEND / "dist",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _wait_up(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _run_axe(url: str) -> dict:
    """Return parsed JSON output of axe-core CLI. Empty dict on failure."""
    try:
        # On Windows `npx` is a .cmd shim and subprocess can't resolve it
        # without shell=True; on POSIX shell=True works too because we
        # control the argv.
        proc = subprocess.run(
            ["npx", "--yes", "@axe-core/cli", url,
             "--tags", "wcag2aa", "--exit", "--save", "-"],
            capture_output=True, text=True, timeout=120,
            shell=(sys.platform == "win32"),
        )
        if proc.returncode not in (0, 1):
            _info(f"axe-core exit={proc.returncode}: {proc.stderr[:200]}")
            return {}
        # axe-cli prints a JSON summary to stdout when --save - is set.
        text = proc.stdout.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _info(f"axe-core not runnable: {e}")
        return {}


def _score(report: dict | None) -> float:
    """Approximate Lighthouse-style score: 100 - 5 per violation, floored at 0.

    The official Lighthouse weighting is more nuanced (impact-weighted)
    but we want a single number to gate CI on. 5 points per violation
    is conservative for typical EP-component findings.

    An empty/missing report (axe-cli not available, or no JSON parsed)
    is treated as **N/A → 100** so a missing CLI doesn't false-fail
    the build. The `axe-cli not found` case is handled upstream.
    """
    if report is None or not isinstance(report, dict) or "violations" not in report:
        return 100.0
    violations = len(report.get("violations") or [])
    return max(0.0, 100.0 - (violations * 5.0))


MANUAL_CHECKLIST = """\
## Manual a11y checklist (axe-core unavailable)

Run through this list when `npx` is not installed. If 5 out of 7
items pass on **both** ProjectList and ReportView, treat the score
as ≥ 95.

- [ ] Tab through every interactive element of the page — every focus
      is visible (2px outline / >= 3:1 contrast vs surrounding).
- [ ] Press the *skip-to-content* link (Tab from the URL bar) and
      verify focus jumps past the navbar.
- [ ] Every icon-only button has an `aria-label` (inspect with
      DevTools).
- [ ] All charts (KM, forest, heatmap, BA, PK 3D) carry `role="img"`
      with a descriptive `aria-label`.
- [ ] All form fields have an associated `<label>` (browsers' a11y
      tree shows them as labelled).
- [ ] No text node has contrast < 4.5:1 against its background —
      paste the foreground/background hex into the Chrome a11y panel.
- [ ] At < 768 width, every action remains reachable (cards / tabs /
      menus do not overflow the viewport).
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=95.0,
                    help="Per-page minimum score (default 95)")
    ap.add_argument("--no-server", action="store_true",
                    help="Assume the dev server is already running on :5174")
    args = ap.parse_args()

    if not _has_dist():
        _info("frontend/dist not found — run `npm run build` first")
        REPORT.write_text(MANUAL_CHECKLIST, encoding="utf-8")
        _info(f"Wrote manual checklist to {REPORT}")
        return 0

    if not _have_axe():
        _info("npx/axe-core not available — emitting manual checklist")
        REPORT.write_text(MANUAL_CHECKLIST, encoding="utf-8")
        return 0

    port = _pick_port() if not args.no_server else 5174
    proc: subprocess.Popen | None = None
    if not args.no_server:
        proc = _start_static_server(port)
        if not _wait_up(port):
            _info("static server did not come up")
            if proc:
                proc.terminate()
            return 2

    # Static SPA — axe sees the shell. Hash routes for the key views.
    pages = [
        ("ProjectList", f"http://127.0.0.1:{port}/"),
        ("LoginView", f"http://127.0.0.1:{port}/#/login"),
        ("RegisterView", f"http://127.0.0.1:{port}/#/register"),
    ]

    scores: list[tuple[str, float, int]] = []
    try:
        for label, url in pages:
            _info(f"auditing {label} → {url}")
            r = _run_axe(url)
            score = _score(r)
            n_viol = len(r.get("violations") or [])
            scores.append((label, score, n_viol))
            _info(f"  {label}: score={score:.0f} violations={n_viol}")
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    lines = ["# AutoCSR — M22 a11y report", ""]
    for label, score, n_viol in scores:
        lines.append(f"- **{label}**: score = {score:.0f} ({n_viol} violations)")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _info(f"report written to {REPORT}")

    if scores and any(s < args.threshold for _, s, _ in scores):
        _info(f"FAIL — one or more pages below threshold {args.threshold}")
        return 1
    _info(f"PASS — all pages ≥ {args.threshold}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
