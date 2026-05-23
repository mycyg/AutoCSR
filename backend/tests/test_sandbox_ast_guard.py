"""Edge-case unit tests for the AST whitelist sandbox (M17)."""
from __future__ import annotations

from app.sandbox.ast_guard import check


def test_allows_pandas_descriptive():
    code = (
        "import pandas as pd\n"
        "df = pd.DataFrame({'a': [1, 2, 3]})\n"
        "df['a'].describe()\n"
    )
    res = check(code)
    assert res.ok, res.violations


def test_blocks_os_system_import():
    res = check("import os\nos.system('rm -rf /')\n")
    assert not res.ok
    assert any("os" in v for v in res.violations)


def test_blocks_subprocess_import():
    res = check("from subprocess import run\nrun(['ls'])\n")
    assert not res.ok


def test_blocks_eval_call():
    res = check("eval('1+1')\n")
    assert not res.ok
    assert any("eval" in v for v in res.violations)


def test_blocks_exec_call():
    res = check("exec('print(1)')\n")
    assert not res.ok


def test_blocks_dunder_import_call():
    res = check("__import__('os')\n")
    assert not res.ok


def test_blocks_open_call():
    res = check("open('/etc/passwd').read()\n")
    assert not res.ok


def test_allows_relative_artifact_write_open():
    code = (
        "import json\n"
        "with open('chart.json', 'w', encoding='utf-8') as f:\n"
        "    f.write(json.dumps({'ok': True}))\n"
    )
    res = check(code)
    assert res.ok, res.violations


def test_syntax_error_short_circuits():
    res = check("def foo(:\n")
    assert not res.ok
    assert any("syntax_error" in v for v in res.violations)
