#!/usr/bin/env python3
"""Checks for the migrations gate (.github/workflows/migrations-gate.yml).

``normalize SCHEMA``
    Read a ``pg_dump --schema-only`` of SCHEMA on stdin and print it in a form
    that two installs can be diffed in: the schema name becomes ``SCHEMA``,
    pg_dump's comments, blank lines and per-run ``\\restrict`` keys are dropped,
    and the columns of each table are sorted, because an upgraded install can
    hold a column at another position than a fresh one.

``check-indexes --previous-versions FILE``
    Fail when a migration whose version is not listed in FILE (one version per
    line: the previous release's ``schema_migrations``) builds a plain index on
    a table in ``LARGE_TABLES`` that no earlier migration created: a ``CREATE
    INDEX`` without ``CONCURRENTLY``, or an ``ALTER TABLE`` adding a ``UNIQUE``,
    ``PRIMARY KEY`` or ``EXCLUDE`` constraint without ``USING INDEX``. Bootstrap's
    unversioned DDL, which runs after the migrations on every install, fails
    the same way, except for the indexes in ``UNVERSIONED_INDEXES_BEFORE_GATE``.
    A plain index build blocks writes to the table until it ends, so such an
    index must use the online kind, ``CREATE INDEX CONCURRENTLY`` (ADR-028).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

# Tables that grow with use on existing installs: a plain index build on one
# of them stalls running agents during an upgrade (ADR-028).
LARGE_TABLES = frozenset(
    {
        "artifact_derivatives",
        "audit_events",
        "channel_gateway_events",
        "knowledge_chunks",
        "knowledge_embeddings",
        "memory_recall_audit",
        "napkin_log",
        "query_history",
        "retrieval_trace_hits",
        "retrieval_traces",
        "runtime_events",
        "runtime_resource_samples",
        "scheduled_job_events",
        "scheduled_job_runs",
        "squad_messages",
        "tasks",
    }
)

# Plain index builds in bootstrap's unversioned DDL that predate this gate: on
# an existing install they are already built, and IF NOT EXISTS skips them.
UNVERSIONED_INDEXES_BEFORE_GATE = frozenset(
    {
        "idx_artifact_derivatives_vector_hnsw",
        "idx_knowledge_embeddings_vector_hnsw",
    }
)

_TABLE = r'(?P<table>(?:"[^"]+"|[\w{}]+)(?:\.(?:"[^"]+"|\w+))?)'
_CREATE_INDEX_RE = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?P<concurrently>CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    r'(?:(?P<name>"[^"]+"|\w+)\s+)?ON\s+(?:ONLY\s+)?' + _TABLE,
    re.IGNORECASE,
)
_CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _TABLE, re.IGNORECASE)
# An ALTER TABLE that adds one of these constraints builds its index in the
# statement, unless the constraint takes over an index built before it.
_ALTER_TABLE_RE = re.compile(
    r"\bALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?" + _TABLE + r"(?P<actions>[^;]*)", re.IGNORECASE
)
_INDEX_CONSTRAINT_RE = re.compile(r"\b(?:UNIQUE|PRIMARY\s+KEY|EXCLUDE)\b(?!\s+USING\s+INDEX\b)", re.IGNORECASE)


def normalize_dump(text: str, schema: str) -> str:
    schema_re = re.compile(rf'(?<![\w"]){re.escape(schema)}(?![\w"])|"{re.escape(schema)}"')
    lines: list[str] = []
    columns: list[str] | None = None
    for raw in text.splitlines():
        if not raw.strip() or raw.startswith("--") or raw.startswith(("\\restrict ", "\\unrestrict ")):
            continue
        line = schema_re.sub("SCHEMA", raw)
        if columns is not None:
            if line.startswith(")"):
                lines.extend(sorted(column.rstrip(",") for column in columns))
                lines.append(line)
                columns = None
            else:
                columns.append(line)
            continue
        lines.append(line)
        if line.startswith("CREATE TABLE ") and line.endswith("("):
            columns = []
    return "\n".join(lines) + "\n"


def _table_name(qualified: str) -> str:
    return qualified.rsplit(".", 1)[-1].strip('"').lower()


def _plain_index_builds(statement: str) -> list[tuple[str, str, str]]:
    """Return (table, index name or "", problem) for each index the statement builds without CONCURRENTLY."""
    builds: list[tuple[str, str, str]] = []
    for match in _CREATE_INDEX_RE.finditer(statement):
        if not match.group("concurrently"):
            table = _table_name(match.group("table"))
            name = (match.group("name") or "").strip('"').lower()
            builds.append(
                (
                    table,
                    name,
                    f"plain CREATE INDEX on large table {table}; "
                    "build it with CREATE INDEX CONCURRENTLY (the online kind, ADR-028)",
                )
            )
    for match in _ALTER_TABLE_RE.finditer(statement):
        if _INDEX_CONSTRAINT_RE.search(match.group("actions")):
            table = _table_name(match.group("table"))
            builds.append(
                (
                    table,
                    "",
                    f"ALTER TABLE on large table {table} adds a constraint that builds its index; build the index "
                    "with CREATE INDEX CONCURRENTLY (the online kind, ADR-028), then ADD CONSTRAINT ... USING INDEX",
                )
            )
    return builds


def transactional_indexes_on_large_tables(migrations: Iterable[Any], *, previous_versions: set[str]) -> list[str]:
    problems: list[str] = []
    created_before: set[str] = set()
    for migration in migrations:
        created = {
            _table_name(match.group("table"))
            for statement in migration.statements
            for match in _CREATE_TABLE_RE.finditer(statement)
        }
        # A table no earlier migration created is new, so empty while the
        # migration builds its indexes. CREATE TABLE IF NOT EXISTS of an
        # existing table leaves it as it is, populated.
        new_tables = created - created_before
        created_before |= created
        if migration.version in previous_versions:
            continue
        for statement in migration.statements:
            for table, _name, problem in _plain_index_builds(statement):
                if table in LARGE_TABLES and table not in new_tables:
                    problems.append(f"{migration.version}: {problem}")
    return problems


def transactional_indexes_in_unversioned_ddl(statements: Iterable[str]) -> list[str]:
    problems: list[str] = []
    for statement in statements:
        for table, name, problem in _plain_index_builds(statement):
            if table in LARGE_TABLES and name not in UNVERSIONED_INDEXES_BEFORE_GATE:
                problems.append(f"bootstrap's unversioned DDL, which runs on every install: {problem}")
    return problems


def _backend() -> Any:
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    return KnowledgeV2PostgresBackend(agent_id=None, dsn="", schema="knowledge_v2", embedding_dimension=1024)


def current_migrations() -> tuple[Any, ...]:
    return tuple(_backend()._migrations())  # noqa: SLF001 - the gate reads the registry


def current_unversioned_statements() -> tuple[str, ...]:
    return tuple(_backend()._unversioned_vector_statements())  # noqa: SLF001 - the gate reads the registry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    normalize = commands.add_parser("normalize")
    normalize.add_argument("schema")
    check = commands.add_parser("check-indexes")
    check.add_argument("--previous-versions", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "normalize":
        sys.stdout.write(normalize_dump(sys.stdin.read(), args.schema))
        return 0
    previous = {line.strip() for line in args.previous_versions.read_text(encoding="utf-8").splitlines()}
    problems = transactional_indexes_on_large_tables(current_migrations(), previous_versions=previous - {""})
    problems += transactional_indexes_in_unversioned_ddl(current_unversioned_statements())
    for problem in problems:
        sys.stderr.write(f"error: {problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
