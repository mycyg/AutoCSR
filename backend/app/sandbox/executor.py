"""Subprocess-isolated sandbox executor.

Public entrypoint :func:`execute_python` takes a code string, validates it
through :mod:`app.sandbox.ast_guard`, then runs it in a
``multiprocessing.Process`` with:

  - cwd pinned to ``data/projects/<pid>/sandbox/<run_id>/``
  - stdout / stderr captured to text files in that directory
  - wall-clock timeout enforced by the parent (``proc.join(timeout)``)
  - memory cap:
      * Linux/Mac: ``resource.setrlimit`` in the child before user code runs.
      * Windows: a psutil-driven monitor in the parent samples RSS and
        terminates the child if it exceeds the limit. Sampling error is
        ~100 MB by design (sleep granularity).
  - a runtime ``open()`` wrapper restricts writes to the sandbox cwd.

After the child exits, all PNG / parquet / csv files in the sandbox dir
are collected as ``artifacts``.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import platform
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.observability.logger import get_logger
from app.sandbox.ast_guard import check as ast_check


_IS_WINDOWS = platform.system().lower().startswith("win")
logger = get_logger("Sandbox")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SandboxResult:
    run_id: str
    project_id: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    artifacts: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    error: str | None = None       # high-level error code: "ast"|"timeout"|"oom"|"crash"|None
    workdir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "artifacts": list(self.artifacts),
            "violations": list(self.violations),
            "error": self.error,
            "workdir": self.workdir,
        }


# ---------------------------------------------------------------------------
# Child-side runner
# ---------------------------------------------------------------------------

_RUNNER_TEMPLATE = '''
import builtins as _b
import os as _os
import sys as _sys
import sysconfig as _sc

_ALLOWED_ROOT = _os.path.abspath(_os.getcwd())
# Python install + site-packages are read-allowed (matplotlib, pandas, etc.
# load resource files from there). They must NEVER be writable from user code.
_PYROOTS = []
try:
    for _p in (_sys.prefix, _sys.base_prefix, _sc.get_paths().get("data", ""),
                _sc.get_paths().get("stdlib", ""),
                _sc.get_paths().get("purelib", ""),
                _sc.get_paths().get("platlib", "")):
        if _p:
            _PYROOTS.append(_os.path.abspath(_p))
except Exception:
    pass
# Add site-packages directories
try:
    import site as _site
    for _p in _site.getsitepackages() or []:
        _PYROOTS.append(_os.path.abspath(_p))
    if hasattr(_site, "getusersitepackages"):
        _PYROOTS.append(_os.path.abspath(_site.getusersitepackages()))
except Exception:
    pass
# Local data files (matplotlib, certifi, etc.) often live in site-packages
# subtrees; that is already covered by the entries above.
_PYROOTS = [p for p in _PYROOTS if p]

_REAL_OPEN = _b.open


def _safe_open(file, mode="r", *args, **kwargs):
    p = _os.path.abspath(str(file))
    extra = (_os.environ.get("SANDBOX_EXTRA") or "").split(_os.pathsep)
    extra = [e for e in extra if e]
    is_under_root = p == _ALLOWED_ROOT or p.startswith(_ALLOWED_ROOT + _os.sep)
    is_in_extra = any(p == _os.path.abspath(e) for e in extra)
    is_in_python = any(p == r or p.startswith(r + _os.sep) for r in _PYROOTS)
    write_modes = ("w", "a", "x", "+")
    is_write = any(ch in str(mode) for ch in write_modes)
    if is_write and not is_under_root:
        # writes always forbidden outside sandbox cwd
        raise PermissionError(f"sandbox: writing outside cwd not allowed: {{p}}")
    if not (is_under_root or is_in_extra or is_in_python):
        raise PermissionError(f"sandbox: reading outside allowed paths not allowed: {{p}}")
    return _REAL_OPEN(file, mode, *args, **kwargs)


_b.open = _safe_open

# Optional Linux resource caps before any user code runs.
try:
    if _sys.platform.startswith("linux") or _sys.platform == "darwin":
        import resource
        _mem_mb = int(_os.environ.get("SANDBOX_MEM_MB", "512"))
        _mem_bytes = max(64, _mem_mb) * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (_mem_bytes, _mem_bytes))
        except (ValueError, OSError):
            pass
        _cpu_s = int(_os.environ.get("SANDBOX_TIMEOUT_S", "30")) + 2
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (_cpu_s, _cpu_s + 1))
        except (ValueError, OSError):
            pass
except Exception:
    pass

# Run the user code at module scope so they can `import pandas as pd` etc.
USER_CODE = {user_code!r}
exec(compile(USER_CODE, "<sandbox>", "exec"), {{"__name__": "__main__"}})
'''


def _build_runner_script(user_code: str) -> str:
    return _RUNNER_TEMPLATE.format(user_code=user_code)


def _child_entrypoint(script: str, workdir: str, stdout_path: str,
                       stderr_path: str, env_extras: dict[str, str]) -> None:
    """Process target — redirect IO, set env, exec the runner script.

    Runs in a fresh interpreter (multiprocessing default start method on
    Windows is "spawn"; we force "spawn" universally for determinism).
    """
    os.chdir(workdir)
    for k, v in env_extras.items():
        os.environ[k] = v
    sys.stdout = open(stdout_path, "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stderr = open(stderr_path, "w", encoding="utf-8", buffering=1)  # noqa: SIM115
    # Headless matplotlib
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        exec(compile(script, "<sandbox-runner>", "exec"), {"__name__": "__main__"})
    except SystemExit:
        raise
    except MemoryError:
        # Linux RLIMIT_AS surfaces here as MemoryError; surface as nonzero exit
        print("[sandbox] MemoryError", file=sys.stderr)
        os._exit(137)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        os._exit(1)


# ---------------------------------------------------------------------------
# Parent-side helpers
# ---------------------------------------------------------------------------

def _project_root(project_id: str) -> Path:
    return data_dir() / "projects" / project_id


def _sandbox_dir(project_id: str, run_id: str) -> Path:
    d = _project_root(project_id) / "sandbox" / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "artifacts").mkdir(exist_ok=True)
    return d


def _collect_artifacts(sandbox_dir: Path) -> list[str]:
    out: list[str] = []
    for ext in ("*.png", "*.jpg", "*.svg", "*.pdf", "*.parquet", "*.csv",
                 "*.html", "*.json"):
        # Look in both sandbox_dir/artifacts and the cwd itself
        for p in sandbox_dir.glob(ext):
            out.append(str(p.resolve()))
        for p in (sandbox_dir / "artifacts").glob(ext):
            out.append(str(p.resolve()))
    # dedup while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for path in out:
        if path in seen:
            continue
        seen.add(path)
        uniq.append(path)
    return uniq


def _write_meta(sandbox_dir: Path, result: SandboxResult, code: str) -> None:
    (sandbox_dir / "code.py").write_text(code, encoding="utf-8")
    meta = {
        "run_id": result.run_id,
        "project_id": result.project_id,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "artifacts": [str(p) for p in result.artifacts],
        "violations": list(result.violations),
        "error": result.error,
        "ts": int(time.time()),
    }
    (sandbox_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def _run_with_limits(script: str, workdir: Path, stdout_path: Path,
                      stderr_path: Path, *, timeout: int, mem_mb: int,
                      env_extras: dict[str, str]) -> tuple[int, str | None]:
    """Spawn the child and enforce limits.

    Returns ``(exit_code, error_code)``. ``error_code`` is one of
    ``None``, ``"timeout"``, ``"oom"``, ``"crash"``.
    """
    ctx = mp.get_context("spawn")
    env_extras = {**env_extras,
                   "SANDBOX_TIMEOUT_S": str(timeout),
                   "SANDBOX_MEM_MB": str(mem_mb)}
    proc = ctx.Process(
        target=_child_entrypoint,
        args=(script, str(workdir), str(stdout_path), str(stderr_path),
              env_extras),
    )
    proc.start()

    stop_monitor = threading.Event()
    monitor_error: dict[str, str | None] = {"reason": None}

    def _windows_memory_monitor() -> None:
        """Best-effort RSS monitor for Windows (no RLIMIT_AS)."""
        try:
            import psutil  # type: ignore
        except ImportError:
            return
        try:
            pp = psutil.Process(proc.pid)
        except Exception:
            return
        limit_bytes = mem_mb * 1024 * 1024
        while not stop_monitor.is_set():
            if not proc.is_alive():
                return
            try:
                rss = pp.memory_info().rss
                # Include children just in case
                for ch in pp.children(recursive=True):
                    try:
                        rss += ch.memory_info().rss
                    except Exception:
                        pass
            except Exception:
                return
            if rss > limit_bytes:
                monitor_error["reason"] = "oom"
                try:
                    pp.kill()
                except Exception:
                    pass
                return
            time.sleep(0.5)

    monitor_thread: threading.Thread | None = None
    if _IS_WINDOWS:
        monitor_thread = threading.Thread(target=_windows_memory_monitor,
                                           daemon=True)
        monitor_thread.start()

    proc.join(timeout=timeout)
    error_code: str | None = None
    if proc.is_alive():
        error_code = "timeout"
        try:
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join(2)
        except Exception:
            pass

    stop_monitor.set()
    if monitor_thread is not None:
        monitor_thread.join(1.0)

    exit_code = proc.exitcode if proc.exitcode is not None else -1
    if error_code is None and monitor_error["reason"]:
        error_code = monitor_error["reason"]
    if error_code is None and exit_code != 0:
        # Linux RLIMIT_AS produces exit_code 1 + MemoryError on stderr;
        # we'll let the caller decide based on stderr content if needed.
        # CPU rlimit produces SIGXCPU which shows as -24.
        if exit_code in (137, -9, -24):
            error_code = "oom" if exit_code == 137 else "timeout"
        else:
            error_code = "crash"
    return exit_code, error_code


def execute_python(
    project_id: str,
    code: str,
    *,
    timeout: int = 30,
    mem_mb: int = 512,
    allowed_imports: list[str] | None = None,  # currently informational; static AST allowlist applies
    additional_data_paths: list[str | Path] | None = None,
) -> SandboxResult:
    """Run ``code`` in a sandboxed subprocess.

    The ``allowed_imports`` argument is reserved for future use — today the
    AST guard's allowlist is the source of truth. Passing it has no effect
    other than being logged so the caller can verify their intent.

    ``additional_data_paths`` lets the sandbox read specific files outside
    the sandbox dir (e.g. ``data/projects/<pid>/processed/data.parquet``).
    Writes are still confined to the sandbox cwd.
    """
    run_id = uuid.uuid4().hex[:12]
    workdir = _sandbox_dir(project_id, run_id)
    stdout_path = workdir / "stdout.txt"
    stderr_path = workdir / "stderr.txt"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    result = SandboxResult(
        run_id=run_id, project_id=project_id, workdir=str(workdir),
    )

    # 1. Static AST check ---------------------------------------------------
    guard = ast_check(code)
    if not guard.ok:
        result.violations = list(guard.violations)
        result.error = "ast"
        result.exit_code = 2
        result.stderr = "AST guard rejected code:\n" + "\n".join(guard.violations)
        stderr_path.write_text(result.stderr, encoding="utf-8")
        _write_meta(workdir, result, code)
        logger.warning("sandbox.ast_blocked", project_id=project_id,
                       run_id=run_id, violations=guard.violations)
        return result

    extra_paths = [str(Path(p).resolve()) for p in (additional_data_paths or [])
                    if Path(p).exists()]
    env_extras = {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "SANDBOX_EXTRA": os.pathsep.join(extra_paths),
    }
    script = _build_runner_script(code)

    # 2. Run in subprocess --------------------------------------------------
    t0 = time.time()
    try:
        exit_code, error_code = _run_with_limits(
            script, workdir, stdout_path, stderr_path,
            timeout=timeout, mem_mb=mem_mb, env_extras=env_extras,
        )
    except Exception as e:  # noqa: BLE001
        result.exit_code = -1
        result.error = "crash"
        result.stderr = f"sandbox parent crashed: {e}"
        stderr_path.write_text(result.stderr, encoding="utf-8")
        _write_meta(workdir, result, code)
        return result
    duration_ms = int((time.time() - t0) * 1000)

    # 3. Collect output ------------------------------------------------------
    result.exit_code = exit_code
    result.error = error_code
    result.duration_ms = duration_ms
    try:
        result.stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        result.stdout = ""
    try:
        result.stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        result.stderr = ""
    # Recognise Linux memory cap (MemoryError + nonzero) even without monitor
    if error_code in (None, "crash") and "MemoryError" in result.stderr:
        result.error = "oom"
    result.artifacts = _collect_artifacts(workdir)
    _write_meta(workdir, result, code)
    logger.info("sandbox.run_done", project_id=project_id, run_id=run_id,
                exit_code=result.exit_code, error=result.error,
                duration_ms=duration_ms, n_artifacts=len(result.artifacts))
    return result


def list_runs(project_id: str) -> list[dict[str, Any]]:
    """List historical sandbox runs (newest first)."""
    root = _project_root(project_id) / "sandbox"
    if not root.exists():
        return []
    runs: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = d / "meta.json"
        if not meta.exists():
            continue
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
            payload["workdir"] = str(d)
            runs.append(payload)
        except Exception:
            continue
    return runs


def artifact_path(project_id: str, run_id: str, filename: str) -> Path | None:
    """Resolve an artifact file path; returns None if it escapes the sandbox."""
    sandbox = _project_root(project_id) / "sandbox" / run_id
    if not sandbox.exists():
        return None
    candidate = (sandbox / filename).resolve()
    artifacts_sub = (sandbox / "artifacts" / filename).resolve()
    sandbox_resolved = sandbox.resolve()
    for cand in (candidate, artifacts_sub):
        try:
            cand.relative_to(sandbox_resolved)
        except ValueError:
            continue
        if cand.exists() and cand.is_file():
            return cand
    return None
