"""Smoke test for the AutoCSR backend.

Usage:
    python scripts/smoke_test.py [--base http://127.0.0.1:8766]

Exits 0 on success, prints request/response summaries.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import error, request


def _get(url: str, *, timeout: float = 5.0) -> tuple[int, dict]:
    req = request.Request(url, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8")
    try:
        return r.status, json.loads(body)
    except json.JSONDecodeError:
        return r.status, {"_raw": body}


def _post(url: str, payload: dict, *, timeout: float = 60.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8")
    try:
        return r.status, json.loads(body)
    except json.JSONDecodeError:
        return r.status, {"_raw": body}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8766")
    p.add_argument("--retries", type=int, default=10,
                   help="poll the server up to N times waiting for readiness")
    args = p.parse_args()
    base = args.base.rstrip("/")

    print(f"[smoke] base={base}")

    # 1) /health (with brief readiness poll)
    last_err: Exception | None = None
    for attempt in range(args.retries):
        try:
            status, data = _get(f"{base}/health")
            print(f"[smoke] /health -> {status} {data}")
            if status != 200 or data.get("status") != "ok":
                print(f"[smoke] /health unexpected payload")
                return 2
            break
        except (error.URLError, ConnectionError) as e:
            last_err = e
            print(f"[smoke] /health attempt {attempt+1} not ready: {e}")
            time.sleep(0.6)
    else:
        print(f"[smoke] /health never came up: {last_err}")
        return 3

    # 2) /llm/ping — actually exercise the LLM endpoint
    try:
        status, data = _post(f"{base}/llm/ping",
                             {"q": "Say 'hello' in one word."},
                             timeout=90.0)
    except error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"[smoke] /llm/ping HTTPError {e.code}: {body[:400]}")
        return 4
    reply = (data.get("reply") or "")[:200]
    print(f"[smoke] /llm/ping -> {status}")
    print(f"[smoke]   via={data.get('via')} tokens={data.get('tokens')}")
    print(f"[smoke]   reply={reply!r}")
    if status != 200 or not reply:
        print("[smoke] /llm/ping returned empty reply")
        return 5

    # 3) Projects: list current count, create one, verify it appears
    status, before = _get(f"{base}/api/projects")
    print(f"[smoke] /api/projects (before) -> {status} count={len(before)}")
    status, created = _post(f"{base}/api/projects",
                            {"name": f"smoke-test-{int(time.time())}"})
    print(f"[smoke] POST /api/projects -> {status} id={created.get('id')}")
    if status != 201 or not created.get("id"):
        print("[smoke] project creation failed")
        return 6
    status, after = _get(f"{base}/api/projects")
    if len(after) != len(before) + 1:
        print(f"[smoke] project not persisted (before={len(before)}, after={len(after)})")
        return 7
    print(f"[smoke] OK — backend is alive, LLM reachable, projects CRUD works")
    return 0


if __name__ == "__main__":
    sys.exit(main())
