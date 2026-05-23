"""Launch the arq Worker for AutoCSR.

Used by the docker-compose ``worker`` service and by manual local runs::

    cd backend
    python ../scripts/run_arq_worker.py

Reads queue.redis_url from settings.yaml (env ``AUTOCSR_REDIS_URL``
overrides). When ``arq`` or Redis are unreachable, the script logs and
exits non-zero so the container orchestrator can restart it.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def main() -> int:
    # Allow running from repo root by injecting backend/ on sys.path.
    here = Path(__file__).resolve().parent
    backend = (here.parent / "backend").resolve()
    if backend.exists() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    logging.basicConfig(
        level=os.environ.get("AUTOCSR_WORKER_LOG", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("autocsr.worker")
    log.info("starting arq worker; cwd=%s", os.getcwd())

    try:
        from arq.worker import run_worker  # type: ignore
    except Exception as exc:  # pragma: no cover
        log.error("arq is not installed: %s — install with `pip install arq`", exc)
        return 1

    try:
        from app.queue.arq_app import WorkerSettings
    except Exception as exc:  # pragma: no cover
        log.exception("failed to import WorkerSettings: %s", exc)
        return 1

    try:
        run_worker(WorkerSettings)  # blocks
    except KeyboardInterrupt:
        log.info("worker interrupted; shutting down")
        return 0
    except Exception as exc:  # pragma: no cover
        log.exception("worker crashed: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
