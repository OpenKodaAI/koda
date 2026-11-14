"""Guards that keep the test suite independent of where and how it runs.

- Tests read repository files through paths anchored on ``__file__``, never
  through ``Path("koda/...")`` or ``Path("docs/...")``, which resolve against
  the current directory and break when pytest starts outside the repo root.
- Postgres tests empty squad tables only through
  ``tests.postgres_fixtures.reset_squad_runtime_tables``, so a new squad table
  or foreign key needs one change instead of one per test file.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
_THIS_FILE = Path(__file__).resolve()
_SQUAD_RESET_HELPER = TESTS / "postgres_fixtures.py"

_CWD_RELATIVE_REPO_PATH = re.compile(r"""\bPath\(\s*f?["'](?:\./)?(?:koda|docs)/""")
_SQUAD_TRUNCATE = re.compile(r"\bTRUNCATE\b[^\n]*\bsquad_", re.IGNORECASE)


def _test_sources() -> Iterator[tuple[Path, str]]:
    for path in sorted(TESTS.rglob("*.py")):
        if path == _THIS_FILE:
            continue
        yield path, path.read_text(encoding="utf-8")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


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


def test_squad_tables_are_reset_only_through_the_shared_helper() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{_line_of(text, match.start())}"
        for path, text in _test_sources()
        if path != _SQUAD_RESET_HELPER
        for match in _SQUAD_TRUNCATE.finditer(text)
    ]
    assert offenders == [], (
        f"Use tests.postgres_fixtures.reset_squad_runtime_tables instead of truncating squad tables: {offenders}"
    )


def test_squad_reset_helper_covers_every_squad_table_in_the_schema() -> None:
    from tests.postgres_fixtures import SQUAD_RUNTIME_TABLES

    backend_source = (ROOT / "koda" / "knowledge" / "v2" / "postgres_backend.py").read_text(encoding="utf-8")
    created = set(re.findall(r'CREATE TABLE IF NOT EXISTS "\{schema\}"\."(squad_[a-z_]+)"', backend_source))

    assert created, "no squad tables found in the Postgres migrations; update this guard"
    assert sorted(created - set(SQUAD_RUNTIME_TABLES)) == []
    assert sorted(set(SQUAD_RUNTIME_TABLES) - created) == []
