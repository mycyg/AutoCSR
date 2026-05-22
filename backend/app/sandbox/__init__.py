"""Python code sandbox.

Lets the agent (or human user) run pandas/numpy/matplotlib snippets against
the project's processed parquets, with hardened safety:

  - AST guard rejects ``os``/``subprocess``/``socket``/``eval``/``exec``
    and any import outside a small whitelist (see :mod:`app.sandbox.ast_guard`).
  - Isolated subprocess (multiprocessing) with resource caps:
        * Linux/Mac: ``resource.setrlimit`` on RLIMIT_AS + RLIMIT_CPU.
        * Windows: psutil-driven memory monitor + ``threading.Timer`` for
          wall-clock timeout (best-effort; ±100 MB sampling error).
  - Working directory pinned to
    ``data/projects/<pid>/sandbox/<run_id>/`` so writes can't escape.
"""
from app.sandbox.executor import SandboxResult, execute_python

__all__ = ["execute_python", "SandboxResult"]
