"""The checks behind .github/workflows/migrations-gate.yml (D-106).

The workflow migrates one schema from the previous release to this commit and
one from scratch, then diffs their ``pg_dump``. These tests cover the two
pieces it runs through ``scripts/migrations_gate.py``: the dump normalization
the diff relies on, and the refusal of a new plain ``CREATE INDEX`` on a large
table (ADR-028).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from koda.knowledge.v2.postgres_backend import _Migration

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "migrations_gate.py"
WORKFLOW_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "migrations-gate.yml"


def _gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migrations_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_DUMP = """--
-- PostgreSQL database dump
--

\\restrict {token}

-- Dumped from database version 16.4

SET statement_timeout = 0;

CREATE SCHEMA {schema};

CREATE TABLE {schema}.cp_workspaces (
{columns}
);

CREATE INDEX idx_workspaces_name ON {schema}.cp_workspaces USING btree (name);

\\unrestrict {token}
"""


def _dump(schema: str, columns: list[str], token: str) -> str:
    body = ",\n".join(f"    {column}" for column in columns)
    return _DUMP.format(schema=schema, columns=body, token=token)


def test_normalized_dumps_match_across_schema_names_column_order_and_restrict_keys() -> None:
    gate = _gate()
    fresh = _dump("gate_fresh", ["id text NOT NULL", "name text NOT NULL", "spec_json text"], "abc")
    upgraded = _dump("gate_upgrade", ["id text NOT NULL", "spec_json text", "name text NOT NULL"], "xyz")

    assert gate.normalize_dump(fresh, "gate_fresh") == gate.normalize_dump(upgraded, "gate_upgrade")
    assert "gate_fresh" not in gate.normalize_dump(fresh, "gate_fresh")


def test_normalized_dumps_differ_when_a_column_differs() -> None:
    gate = _gate()
    fresh = _dump("gate_fresh", ["id text NOT NULL", "name text NOT NULL", "drift text"], "abc")
    upgraded = _dump("gate_upgrade", ["id text NOT NULL", "name text NOT NULL"], "abc")

    assert gate.normalize_dump(fresh, "gate_fresh") != gate.normalize_dump(upgraded, "gate_upgrade")


@pytest.mark.parametrize(
    "statement",
    [
        'CREATE INDEX IF NOT EXISTS idx_probe ON "knowledge_v2"."audit_events" (event_type)',
        "create unique index idx_probe on knowledge_v2.query_history (id)",
        'CREATE INDEX idx_probe\n    ON ONLY "{schema}"."napkin_log" USING btree (created_at)',
    ],
)
def test_a_new_plain_create_index_on_a_large_table_is_refused(statement: str) -> None:
    gate = _gate()
    migration = _Migration("099_probe", (statement,))

    problems = gate.transactional_indexes_on_large_tables([migration], previous_versions=set())

    assert len(problems) == 1
    assert problems[0].startswith("099_probe: ")
    assert "CONCURRENTLY" in problems[0]


@pytest.mark.parametrize(
    ("statement", "previous_versions"),
    [
        ('CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_probe ON "knowledge_v2"."audit_events" (event_type)', set()),
        ('CREATE INDEX IF NOT EXISTS idx_probe ON "knowledge_v2"."cp_workspaces" (name)', set()),
        ('CREATE INDEX IF NOT EXISTS idx_probe ON "knowledge_v2"."audit_events" (event_type)', {"099_probe"}),
    ],
    ids=["concurrently", "small-table", "already-released"],
)
def test_other_index_builds_pass(statement: str, previous_versions: set[str]) -> None:
    gate = _gate()
    migration = _Migration("099_probe", (statement,))

    assert gate.transactional_indexes_on_large_tables([migration], previous_versions=previous_versions) == []


def test_an_index_on_a_large_table_created_by_the_same_migration_passes() -> None:
    gate = _gate()
    migration = _Migration(
        "099_probe",
        (
            'CREATE TABLE IF NOT EXISTS "{schema}"."scheduled_job_events" (id BIGSERIAL PRIMARY KEY)',
            'CREATE INDEX IF NOT EXISTS idx_probe ON "{schema}"."scheduled_job_events" (id DESC)',
        ),
    )

    assert gate.transactional_indexes_on_large_tables([migration], previous_versions=set()) == []


def test_check_indexes_passes_for_this_commit_against_its_own_versions(tmp_path: Path) -> None:
    gate = _gate()
    versions = tmp_path / "previous_versions.txt"
    versions.write_text("\n".join(m.version for m in gate.current_migrations()) + "\n", encoding="utf-8")

    repo_root = SCRIPT_PATH.parents[1]
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "check-indexes", "--previous-versions", str(versions)],
        capture_output=True,
        text=True,
        check=False,
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    assert result.returncode == 0, result.stderr


def test_check_indexes_fails_when_a_new_migration_builds_a_plain_index_on_a_large_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = _gate()
    released = gate.current_migrations()
    probe = _Migration("999_probe", ('CREATE INDEX IF NOT EXISTS idx_probe ON "s"."query_history" (agent_id)',))
    monkeypatch.setattr(gate, "current_migrations", lambda: (*released, probe))
    versions = tmp_path / "previous_versions.txt"
    versions.write_text("\n".join(m.version for m in released) + "\n", encoding="utf-8")

    assert gate.main(["check-indexes", "--previous-versions", str(versions)]) == 1
    assert "999_probe" in capsys.readouterr().err


def test_workflow_diffs_an_upgrade_from_the_previous_release_against_a_fresh_install() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "uv sync --locked" in workflow
    assert "pip install" not in workflow
    assert "git describe --tags --abbrev=0" in workflow
    assert "--schema gate_upgrade" in workflow and "--schema gate_fresh" in workflow
    assert "scripts/migrations_gate.py normalize" in workflow
    assert "scripts/migrations_gate.py check-indexes" in workflow
