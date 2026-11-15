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
    line: the previous release's ``schema_migrations``) runs a plain
    ``CREATE INDEX`` on a table in ``LARGE_TABLES`` that the migration does not
    create itself. A plain index build blocks writes to the table until it
    ends, so such an index must use the online kind, ``CREATE INDEX
    CONCURRENTLY`` (ADR-028).
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

_TABLE = r'(?P<table>(?:"[^"]+"|[\w{}]+)(?:\.(?:"[^"]+"|\w+))?)'
_CREATE_INDEX_RE = re.compile(
    r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?P<concurrently>CONCURRENTLY\b)?.*?\bON\s+(?:ONLY\s+)?" + _TABLE,
    re.IGNORECASE | re.DOTALL,
)
_CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _TABLE, re.IGNORECASE)


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


def transactional_indexes_on_large_tables(migrations: Iterable[Any], *, previous_versions: set[str]) -> list[str]:
    problems: list[str] = []
    for migration in migrations:
        if migration.version in previous_versions:
            continue
        # A table the migration creates is empty while its indexes are built.
        created = {
            _table_name(match.group("table"))
            for statement in migration.statements
            for match in _CREATE_TABLE_RE.finditer(statement)
        }
        for statement in migration.statements:
            for match in _CREATE_INDEX_RE.finditer(statement):
                table = _table_name(match.group("table"))
                if table in LARGE_TABLES and table not in created and not match.group("concurrently"):
                    problems.append(
                        f"{migration.version}: plain CREATE INDEX on large table {table}; "
                        "build it with CREATE INDEX CONCURRENTLY (the online kind, ADR-028)"
                    )
    return problems


def current_migrations() -> tuple[Any, ...]:
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    backend = KnowledgeV2PostgresBackend(agent_id=None, dsn="", schema="knowledge_v2", embedding_dimension=1024)
    return tuple(backend._migrations())  # noqa: SLF001 - the gate reads the registry


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
    for problem in problems:
        sys.stderr.write(f"error: {problem}\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
