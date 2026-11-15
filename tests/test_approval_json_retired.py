"""No code writes approval JSON: Postgres is the only approval store (M2-E1-T2).

Earlier releases fell back to ``approval_grants.json`` and ``pending_approvals.json``
in STATE_ROOT_DIR when a Postgres write failed. The only code that still names those
files is the startup import, which reads each file and renames it ``*.migrated``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_KODA = _ROOT / "koda"
_FILE_NAMES = ("approval_grants.json", "pending_approvals.json")
_IMPORT_MODULE = _KODA / "state" / "approval_import.py"
_WRITE_CALLS = {"write_text", "write_bytes", "dump", "open", "mkdir", "touch", "replace", "unlink"}


def _docstrings(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _modules_naming_the_files() -> set[Path]:
    found = set()
    for path in _KODA.rglob("*.py"):
        if "generated" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
                and any(name in node.value for name in _FILE_NAMES)
            ):
                found.add(path)
    return found


def test_only_the_startup_import_names_the_approval_json_files() -> None:
    assert _modules_naming_the_files() == {_IMPORT_MODULE}


def test_the_startup_import_reads_and_renames_but_writes_nothing() -> None:
    tree = ast.parse(_IMPORT_MODULE.read_text(encoding="utf-8"))
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "read_text" in calls and "rename" in calls
    assert not calls & _WRITE_CALLS, sorted(calls & _WRITE_CALLS)


def test_the_approval_stores_have_no_file_path() -> None:
    for name in ("approval_grants.py", "pending_approvals.py"):
        source = (_KODA / "state" / name).read_text(encoding="utf-8")
        assert "STATE_ROOT_DIR" not in source, name


def test_the_worker_runs_the_import_at_startup() -> None:
    source = (_KODA / "__main__.py").read_text(encoding="utf-8")
    assert "await import_approval_json_files()" in source
