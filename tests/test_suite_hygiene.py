"""Guards that keep the test suite independent of where and how it runs.

- Tests read repository files through paths anchored on ``__file__``, so
  they pass when pytest starts outside the repo root. Two shapes in test
  code are rejected: a ``Path("koda/...")``-style literal naming a
  repository entry that is read (``Path(...).read_text()``, ``open(...)``,
  ``.glob()``, ``.exists()``...), and a helper that reads
  ``Path(<its own parameter>)`` instead of joining the parameter onto an
  anchored root (``_read_source("koda/x.py")`` callers cannot see that the
  helper is cwd-relative). The check is static and stops at the test file:
  a relative path handed to code under test that resolves it against the
  cwd is invisible to it (``scripts/review_dependency_changes.py`` resolves
  a Cargo manifest's directory this way). Such tests pass an anchored path
  and, where the behaviour depends on it, run under
  ``monkeypatch.chdir(tmp_path)``.
- Postgres tests empty squad tables only through
  ``tests.postgres_fixtures.reset_squad_runtime_tables``, so a new squad table
  or foreign key needs one change instead of one per test file.
- Tests reset the shared Postgres backends only through
  ``tests.postgres_fixtures.close_shared_postgres_backends``, which closes
  their pools; clearing the cache directly leaks connections (D-225).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
_THIS_FILE = Path(__file__).resolve()
_POSTGRES_FIXTURES = TESTS / "postgres_fixtures.py"

_CWD_RELATIVE_REPO_PATH = re.compile(r"""\bPath\(\s*f?["'](?:\./)?(?:koda|docs)/""")
_SQUAD_TRUNCATE = re.compile(r"\bTRUNCATE\b[^\n]*\bsquad_", re.IGNORECASE)
_SHARED_BACKEND_CACHE_CLEAR = re.compile(r"_SHARED_POSTGRES_BACKENDS\.clear\(\)")

# Names at the repository root (koda, docs, apps, README.md, ...): a relative
# path starting with one of them only resolves when the cwd is the repo root.
_REPO_ENTRIES = frozenset(entry.name for entry in ROOT.iterdir()) - {".git"}
# Path methods that touch the filesystem, so their result depends on the cwd
# when the path is relative.
_PATH_FILESYSTEM_METHODS = frozenset(
    {"read_text", "read_bytes", "open", "exists", "is_file", "is_dir", "iterdir", "glob", "rglob", "stat"}
)
# Path methods whose result is still the same (possibly relative) location.
_PATH_PASSTHROUGH_METHODS = frozenset({"resolve", "absolute", "expanduser"})
_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _test_sources() -> Iterator[tuple[Path, str]]:
    for path in sorted(TESTS.rglob("*.py")):
        if path == _THIS_FILE:
            continue
        yield path, path.read_text(encoding="utf-8")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    scope = parents.get(node)
    while scope is not None and not isinstance(scope, _FUNCTION_SCOPES):
        scope = parents.get(scope)
    return scope


def _parameters_of_enclosing_function(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> set[str]:
    scope = _enclosing_function(node, parents)
    if not isinstance(scope, _FUNCTION_SCOPES):
        return set()
    arguments = scope.args
    return {argument.arg for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}


def _is_path_constructor(func: ast.expr) -> bool:
    return (isinstance(func, ast.Name) and func.id == "Path") or (
        isinstance(func, ast.Attribute) and func.attr == "Path"
    )


def _is_builtin_open(func: ast.expr) -> bool:
    return isinstance(func, ast.Name) and func.id == "open"


def _names_repository_entry(node: ast.expr) -> bool:
    """A string literal, or an f-string's literal head, whose first path
    segment is an entry at the repository root."""
    if isinstance(node, ast.JoinedStr) and node.values:
        node = node.values[0]
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    return node.value.removeprefix("./").split("/", 1)[0] in _REPO_ENTRIES


def _path_touches_filesystem(path_call: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """Whether the Path built by ``path_call`` reaches the filesystem, possibly
    after ``/ "child"`` joins or ``.resolve()``-style calls."""
    current: ast.AST = path_call
    while True:
        parent = parents.get(current)
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and parent.left is current:
            current = parent
            continue
        if isinstance(parent, ast.Attribute) and parent.attr in _PATH_PASSTHROUGH_METHODS:
            call = parents.get(parent)
            if isinstance(call, ast.Call) and call.func is parent:
                current = call
                continue
        if isinstance(parent, ast.Attribute):
            return parent.attr in _PATH_FILESYSTEM_METHODS
        if isinstance(parent, ast.Call):
            return _is_builtin_open(parent.func) and bool(parent.args) and parent.args[0] is current
        return False


def _cwd_relative_reads(source: str) -> list[int]:
    """Lines where ``source`` reaches a repository file through a path that
    resolves against the current directory."""
    tree = ast.parse(source)
    parents = _parent_map(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        target = node.args[0]
        if _is_builtin_open(node.func):
            if _names_repository_entry(target):
                lines.append(node.lineno)
            continue
        if not _is_path_constructor(node.func) or not _path_touches_filesystem(node, parents):
            continue
        if _names_repository_entry(target) or (
            isinstance(target, ast.Name) and target.id in _parameters_of_enclosing_function(node, parents)
        ):
            lines.append(node.lineno)
    return sorted(lines)


def test_tests_anchor_repository_paths_on_their_own_location() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{_line_of(text, match.start())}"
        for path, text in _test_sources()
        for match in _CWD_RELATIVE_REPO_PATH.finditer(text)
    ]
    assert offenders == [], (
        "Read repository files through Path(__file__).resolve().parents[N] so the test "
        f"passes from any working directory: {offenders}"
    )


def test_tests_do_not_read_repository_files_relative_to_the_cwd() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{line}" for path, text in _test_sources() for line in _cwd_relative_reads(text)
    ]
    assert offenders == [], (
        "Join repository paths onto ROOT = Path(__file__).resolve().parents[N] (helpers included: "
        f"(ROOT / rel_path).read_text(), not Path(rel_path).read_text()): {offenders}"
    )


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        pytest.param('Path("koda/__main__.py").read_text()', True, id="literal-read"),
        pytest.param('open("docs/README.md")', True, id="builtin-open"),
        pytest.param('(Path("apps") / "web" / "package.json").read_text()', True, id="joined-literal"),
        pytest.param('pathlib.Path(f"docs/{name}.md").resolve().read_text()', True, id="fstring-resolved"),
        pytest.param('Path("README.md").exists()', True, id="root-file-probe"),
        pytest.param(
            "def _read_source(rel_path):\n    return Path(rel_path).read_text(encoding='utf-8')\n",
            True,
            id="helper-reads-its-parameter",
        ),
        pytest.param('(ROOT / "koda" / "__main__.py").read_text()', False, id="anchored-read"),
        pytest.param("def _read(rel):\n    return (ROOT / rel).read_text()\n", False, id="anchored-helper"),
        pytest.param('check(Path("apps/web/package.json"))', False, id="literal-label-not-read"),
        pytest.param('(tmp_path / "out.txt").read_text()', False, id="tmp-path-read"),
        pytest.param('Path("notes.txt").read_text()', False, id="non-repository-literal"),
    ],
)
def test_cwd_relative_read_detection(source: str, flagged: bool) -> None:
    assert bool(_cwd_relative_reads(source)) is flagged


def test_squad_tables_are_reset_only_through_the_shared_helper() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{_line_of(text, match.start())}"
        for path, text in _test_sources()
        if path != _POSTGRES_FIXTURES
        for match in _SQUAD_TRUNCATE.finditer(text)
    ]
    assert offenders == [], (
        f"Use tests.postgres_fixtures.reset_squad_runtime_tables instead of truncating squad tables: {offenders}"
    )


def test_shared_postgres_backends_are_reset_only_through_the_closing_helper() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{_line_of(text, match.start())}"
        for path, text in _test_sources()
        if path != _POSTGRES_FIXTURES
        for match in _SHARED_BACKEND_CACHE_CLEAR.finditer(text)
    ]
    assert offenders == [], (
        f"Use tests.postgres_fixtures.close_shared_postgres_backends so the dropped pools are closed: {offenders}"
    )


def test_postgres_fixtures_clear_the_backend_cache_only_inside_the_closing_helper() -> None:
    """The fixtures module may empty the cache, but only after closing the
    pools, i.e. inside ``close_shared_postgres_backends``."""
    tree = ast.parse(_POSTGRES_FIXTURES.read_text(encoding="utf-8"))
    parents = _parent_map(tree)
    clear_sites = [
        (getattr(_enclosing_function(node, parents), "name", "<module>"), node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "clear"
        and _SHARED_BACKEND_CACHE_CLEAR.search(ast.unparse(node))
    ]

    assert clear_sites, "close_shared_postgres_backends no longer empties the cache; update this guard"
    assert [site for site in clear_sites if site[0] != "close_shared_postgres_backends"] == []


def test_squad_reset_helper_covers_every_squad_table_in_the_schema() -> None:
    from tests.postgres_fixtures import SQUAD_RUNTIME_TABLES

    backend_source = (ROOT / "koda" / "knowledge" / "v2" / "postgres_backend.py").read_text(encoding="utf-8")
    created = set(re.findall(r'CREATE TABLE IF NOT EXISTS "\{schema\}"\."(squad_[a-z_]+)"', backend_source))

    assert created, "no squad tables found in the Postgres migrations; update this guard"
    assert sorted(created - set(SQUAD_RUNTIME_TABLES)) == []
    assert sorted(set(SQUAD_RUNTIME_TABLES) - created) == []
