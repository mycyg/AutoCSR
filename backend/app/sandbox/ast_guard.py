"""AST guard for the Python sandbox.

We walk the parsed AST and reject any construct that could exfiltrate or
mutate state outside the sandbox directory. Regex matching is *not* used
because it is trivially bypassed (e.g. via string concatenation).

Allow-list:
  * Imports of modules in :data:`ALLOWED_IMPORTS` or :data:`STDLIB_ALLOWED`.
  * Calls to *any* function/method except those explicitly banned in
    :data:`BANNED_CALLS`.

Disallow:
  * ``import os``, ``import subprocess``, ``import socket``, etc.
  * ``__import__``, ``eval``, ``exec``, ``compile``.
  * ``open(..., 'w'+)`` (write) and any ``open(...)`` with absolute paths
    that escape the sandbox cwd.
  * Attribute access like ``foo.os.system`` (string match on the AST attr).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


# Modules a typical analysis snippet legitimately needs.
ALLOWED_IMPORTS: set[str] = {
    "pandas", "numpy", "scipy", "matplotlib", "matplotlib.pyplot",
    "plotly", "plotly.express", "plotly.graph_objects", "plotly.io",
    "lifelines", "statsmodels", "statsmodels.api",
    "seaborn", "sklearn", "tabulate",
}

# Small subset of the stdlib that is harmless for data work.
STDLIB_ALLOWED: set[str] = {
    "math", "json", "re", "datetime", "collections", "itertools",
    "functools", "statistics", "decimal", "fractions",
    "string", "textwrap", "operator", "typing",
}

# Functions we never want called.
BANNED_NAMES: set[str] = {
    "__import__", "eval", "exec", "compile", "globals", "locals",
    "vars", "input", "open",  # `open` re-allowed via runtime wrapper in executor
    "breakpoint", "exit", "quit",
}

# Attribute chains that should never appear. Each entry must match the *full*
# dotted suffix used in the snippet (e.g. ``os.system``, ``subprocess.run``).
BANNED_ATTR_CHAINS: set[str] = {
    "os.system", "os.popen", "os.execv", "os.execvp", "os.spawnv",
    "os.kill", "os.remove", "os.rmdir", "os.unlink",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output",
    "subprocess.getoutput", "subprocess.getstatusoutput",
    "socket.socket", "socket.create_connection",
    "shutil.rmtree", "shutil.move",
    "importlib.import_module", "importlib.reload",
    "ctypes.CDLL", "ctypes.WinDLL", "ctypes.cdll",
    "sys.exit", "sys.modules",
}

# Modules that, if imported, are an instant veto.
BLOCKED_IMPORT_ROOTS: set[str] = {
    "os", "subprocess", "socket", "shutil", "ctypes",
    "multiprocessing", "threading", "importlib", "pathlib",  # path traversal vector
    "sys", "platform", "pickle",
    "http", "urllib", "requests", "httpx", "aiohttp",
    "asyncio", "concurrent",
    "builtins",
}


@dataclass
class GuardResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def _dotted(node: ast.AST) -> str | None:
    """Return ``foo.bar.baz`` for an AST Attribute chain, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _import_module_root(name: str) -> str:
    return name.split(".", 1)[0]


def _is_allowed_import(mod: str) -> bool:
    root = _import_module_root(mod)
    if root in BLOCKED_IMPORT_ROOTS:
        return False
    if mod in ALLOWED_IMPORTS or root in {m.split(".", 1)[0] for m in ALLOWED_IMPORTS}:
        return True
    if root in STDLIB_ALLOWED:
        return True
    return False


def check(code: str) -> GuardResult:
    """Inspect ``code`` and return ok=False with reasons if anything tripped."""
    violations: list[str] = []
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return GuardResult(ok=False, violations=[f"syntax_error:{e}"])

    for node in ast.walk(tree):
        # Imports ---------------------------------------------------------
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if not _is_allowed_import(mod):
                    violations.append(f"import_blocked:{mod}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if not mod or not _is_allowed_import(mod):
                violations.append(f"import_from_blocked:{mod or '<relative>'}")
        # Calls -----------------------------------------------------------
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in BANNED_NAMES:
                    violations.append(f"banned_call:{func.id}")
            elif isinstance(func, ast.Attribute):
                dotted = _dotted(func)
                if dotted is None:
                    # e.g. (obj).method(...) — we can't statically resolve
                    continue
                if dotted in BANNED_ATTR_CHAINS:
                    violations.append(f"banned_call:{dotted}")
                else:
                    # also ban suffix matches like "x.os.system"
                    for chain in BANNED_ATTR_CHAINS:
                        if dotted.endswith("." + chain) or dotted.endswith("." + chain.split(".", 1)[1]):
                            # only flag if the leading bit looks like the same module
                            if dotted.split(".", 1)[0] == chain.split(".", 1)[0] or (
                                "." + chain) in ("." + dotted):
                                violations.append(f"banned_attr_chain:{dotted}")
                                break
        # Bare name reads of banned identifiers (e.g. __import__('os')) --
        elif isinstance(node, ast.Name):
            if node.id == "__import__":
                violations.append("banned_name:__import__")
        # Attribute reads that look like __builtins__.eval ----------------
        elif isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted in {"builtins.eval", "builtins.exec", "builtins.__import__",
                           "__builtins__.eval", "__builtins__.exec",
                           "__builtins__.__import__"}:
                violations.append(f"banned_builtin_access:{dotted}")

    # Dedup while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in violations:
        if v in seen:
            continue
        seen.add(v)
        uniq.append(v)
    return GuardResult(ok=not uniq, violations=uniq)
