"""The checks behind .github/workflows/migrations-gate.yml (D-106).

The workflow migrates one schema from the previous release to this commit and
one from scratch, then diffs their ``pg_dump``. These tests cover the two
pieces it runs through ``scripts/migrations_gate.py``: the dump normalization
the diff relies on, and the refusal of a new plain ``CREATE INDEX`` on a large
table (ADR-028).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

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
        'ALTER TABLE "{schema}"."query_history" ADD CONSTRAINT uq_probe UNIQUE (agent_id, id)',
        "alter table if exists only knowledge_v2.audit_events add primary key (id)",
        'ALTER TABLE "{schema}"."tasks" ADD CONSTRAINT ex_probe EXCLUDE USING gist (id WITH =)',
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
        ('ALTER TABLE "knowledge_v2"."query_history" ADD CONSTRAINT uq_probe UNIQUE USING INDEX idx_probe', set()),
        ('ALTER TABLE "knowledge_v2"."audit_events" ADD COLUMN IF NOT EXISTS probe TEXT', set()),
    ],
    ids=["concurrently", "small-table", "already-released", "constraint-using-index", "add-column"],
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


def test_a_large_table_re_declared_by_a_later_migration_is_not_exempt() -> None:
    """CREATE TABLE IF NOT EXISTS of a table an earlier migration created leaves it populated."""
    gate = _gate()
    create_table = 'CREATE TABLE IF NOT EXISTS "{schema}"."napkin_log" (id BIGSERIAL PRIMARY KEY)'
    released = _Migration("098_probe", (create_table,))
    redeclared = _Migration(
        "099_probe",
        (
            create_table,
            'CREATE INDEX IF NOT EXISTS idx_probe ON "{schema}"."napkin_log" (id DESC)',
        ),
    )

    problems = gate.transactional_indexes_on_large_tables([released, redeclared], previous_versions={"098_probe"})

    assert len(problems) == 1 and problems[0].startswith("099_probe: ")


def test_the_unversioned_ddl_of_this_commit_passes_the_index_check() -> None:
    gate = _gate()

    assert gate.current_unversioned_statements(), "bootstrap's unversioned DDL is read"
    assert gate.transactional_indexes_in_unversioned_ddl(gate.current_unversioned_statements()) == []


@pytest.mark.parametrize(
    "statement",
    [
        'CREATE INDEX IF NOT EXISTS idx_probe ON "knowledge_v2"."audit_events" (event_type)',
        'ALTER TABLE "knowledge_v2"."query_history" ADD CONSTRAINT uq_probe UNIQUE (agent_id, id)',
    ],
)
def test_a_new_plain_index_build_on_a_large_table_in_the_unversioned_ddl_is_refused(
    statement: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bootstrap runs its unversioned DDL after the migrations on every install, existing ones included."""
    gate = _gate()
    unversioned = gate.current_unversioned_statements()
    monkeypatch.setattr(gate, "current_unversioned_statements", lambda: (*unversioned, statement))
    versions = tmp_path / "previous_versions.txt"
    versions.write_text("\n".join(m.version for m in gate.current_migrations()) + "\n", encoding="utf-8")

    assert gate.main(["check-indexes", "--previous-versions", str(versions)]) == 1
    assert "unversioned" in capsys.readouterr().err


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


@pytest.mark.parametrize("head_tagged", [True, False], ids=["dispatched-on-a-release-tag", "untagged-commit"])
def test_the_previous_release_is_never_the_tag_on_the_checked_commit(tmp_path: Path, head_tagged: bool) -> None:
    """Dispatched on v1.0.19 itself, the gate upgrades from v1.0.18, not from the release under test."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["migrations-drift"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "previous")
    repo = tmp_path / "repo"
    repo.mkdir()
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "gate",
        "GIT_AUTHOR_EMAIL": "gate@example.invalid",
        "GIT_COMMITTER_NAME": "gate",
        "GIT_COMMITTER_EMAIL": "gate@example.invalid",
    }

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, env=git_env, check=True, capture_output=True)

    git("init", "-q")
    for tag in ("v1.0.18", "v1.0.19"):
        git("commit", "--allow-empty", "-qm", tag)
        if tag == "v1.0.18" or head_tagged:
            git("tag", "-a", tag, "-m", tag)
    output = tmp_path / "github_output"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=repo,
        env={**git_env, "GITHUB_OUTPUT": str(output)},
        check=True,
        capture_output=True,
    )

    assert output.read_text(encoding="utf-8") == "tag=v1.0.18\n"


# Migrations merged after the latest release, v1.0.18.
_UNRELEASED_VERSIONS = {
    "047_scheduler_events_and_dispatch_columns",
    "048_control_plane_master_key_fingerprint",
    "049_audit_events_type_lookup",
    "050_approval_tables",
}


def test_the_migrations_added_since_the_latest_release_pass_the_index_check() -> None:
    gate = _gate()
    migrations = gate.current_migrations()
    versions = [m.version for m in migrations]
    # Migrations run in list order, so the unreleased ones are the end of the list.
    assert set(versions[len(versions) - len(_UNRELEASED_VERSIONS) :]) == _UNRELEASED_VERSIONS
    released = set(versions) - _UNRELEASED_VERSIONS

    assert gate.transactional_indexes_on_large_tables(migrations, previous_versions=released) == []


@pytest.mark.postgres
async def test_audit_events_type_index_is_rebuilt_after_a_failed_concurrent_build(migrated_postgres: str) -> None:
    """049 builds its index online; a failed build leaves an INVALID index, which the next run replaces."""
    import asyncpg  # type: ignore[import-not-found]

    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    schema = "gate_invalid_index_probe"
    backend = KnowledgeV2PostgresBackend(agent_id=None, dsn=migrated_postgres, schema=schema)
    migration = next(m for m in backend._migrations() if m.version == "049_audit_events_type_lookup")
    conn = await asyncpg.connect(migrated_postgres)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.execute(f'CREATE SCHEMA "{schema}"')
        await conn.execute(f'CREATE TABLE "{schema}"."audit_events" (event_type TEXT, timestamp TEXT)')
        await conn.execute(f"INSERT INTO \"{schema}\".\"audit_events\" VALUES ('a', 't'), ('a', 't')")
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                f'CREATE UNIQUE INDEX CONCURRENTLY idx_audit_events_type_time ON "{schema}"."audit_events" (event_type)'
            )

        for statement in migration.statements:
            await conn.execute(statement)

        rows = await conn.fetch(
            """
            SELECT i.indisvalid, i.indisunique
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1 AND c.relname = 'idx_audit_events_type_time'
            """,
            schema,
        )
        assert [(row["indisvalid"], row["indisunique"]) for row in rows] == [(True, False)]
    finally:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await conn.close()


@pytest.mark.postgres
async def test_049_leaves_an_index_another_backend_is_building_alone(migrated_postgres: str) -> None:
    """While another bootstrap builds the index online, 049 neither drops it nor queues behind the build.

    An INVALID index is also what a build in progress looks like. Dropping it would queue an ACCESS
    EXCLUSIVE lock that stalls every audit write, and any wait behind the build holds a snapshot the
    build's last phase waits for, so the deadlock detector aborts one of them. 049 fails this
    bootstrap at once instead; it runs again at the next one.
    """
    import asyncpg  # type: ignore[import-not-found]

    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    schema = "gate_index_in_progress_probe"
    backend = KnowledgeV2PostgresBackend(agent_id=None, dsn=migrated_postgres, schema=schema)
    migration = next(m for m in backend._migrations() if m.version == "049_audit_events_type_lookup")
    admin, writer, builder, second = [await asyncpg.connect(migrated_postgres) for _ in range(4)]
    build: asyncio.Task[Any] | None = None
    try:
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        await admin.execute(f'CREATE TABLE "{schema}"."audit_events" (event_type TEXT, timestamp TEXT)')
        await admin.execute(f"INSERT INTO \"{schema}\".\"audit_events\" VALUES ('a', 't')")
        # An open write keeps the other backend's online build waiting, its index INVALID.
        open_write = writer.transaction()
        await open_write.start()
        await writer.execute(f"INSERT INTO \"{schema}\".\"audit_events\" VALUES ('b', 't')")
        build = asyncio.create_task(builder.execute(migration.statements[-1]))
        for _ in range(100):
            if await admin.fetchval(
                "SELECT count(*) FROM pg_stat_progress_create_index WHERE pid = $1 AND index_relid <> 0",
                builder.get_server_pid(),
            ):
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("the online build never started")

        await second.execute("SET lock_timeout = '2s'")
        with pytest.raises(asyncpg.RaiseError, match="being built by another backend"):
            for statement in migration.statements:
                await second.execute(statement)

        await admin.execute("SET lock_timeout = '2s'")
        await admin.execute(f"INSERT INTO \"{schema}\".\"audit_events\" VALUES ('c', 't')")
        await open_write.commit()
        await asyncio.wait_for(build, 30)
        valid = await admin.fetchval(
            """
            SELECT i.indisvalid FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = $1 AND c.relname = 'idx_audit_events_type_time'
            """,
            schema,
        )
        assert valid is True
    finally:
        if build is not None and not build.done():
            build.cancel()
        for conn in (writer, builder, second):
            await conn.close()
        await admin.execute("RESET lock_timeout")
        await admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.close()
