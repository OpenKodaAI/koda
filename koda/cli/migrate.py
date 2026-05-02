"""Deterministic ``python -m koda migrate`` command.

Replaces lazy-on-boot migration as the safe path: a release pipeline
runs ``koda migrate`` once before rolling new code, instead of every
host racing to apply the same migration on its first request. The
runtime ``bootstrap()`` call still applies pending migrations as a
defensive fallback for solo-host development; this CLI is what CI and
operators run before deploys.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from koda.knowledge.config import (
    KNOWLEDGE_V2_EMBEDDING_DIMENSION,
    KNOWLEDGE_V2_POSTGRES_DSN,
    KNOWLEDGE_V2_POSTGRES_SCHEMA,
)
from koda.logging_config import get_logger, setup_logging

log = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m koda migrate",
        description="Apply pending knowledge_v2 schema migrations.",
    )
    parser.add_argument(
        "--dsn",
        default=KNOWLEDGE_V2_POSTGRES_DSN,
        help="Override KNOWLEDGE_V2_POSTGRES_DSN for this run.",
    )
    parser.add_argument(
        "--schema",
        default=KNOWLEDGE_V2_POSTGRES_SCHEMA,
        help="Override KNOWLEDGE_V2_POSTGRES_SCHEMA for this run.",
    )
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=KNOWLEDGE_V2_EMBEDDING_DIMENSION,
        help="Override KNOWLEDGE_V2_EMBEDDING_DIMENSION for this run.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Phase 2C CI gate: connect to the DSN, list pending migration "
            "versions and exit non-zero if any exist. Does NOT apply them. "
            "Use this in release pipelines to refuse a deploy whose code "
            "expects a schema that has not been rolled out yet."
        ),
    )
    return parser


async def _apply(dsn: str, schema: str, embedding_dimension: int) -> bool:
    # Imported lazily so a CLI invocation that fails arg parsing doesn't
    # pay the cost of constructing the backend.
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    backend = KnowledgeV2PostgresBackend(
        agent_id=None,
        dsn=dsn,
        schema=schema,
        embedding_dimension=embedding_dimension,
    )
    return await backend.bootstrap()


async def _pending_versions(dsn: str, schema: str, embedding_dimension: int) -> list[str]:
    """Return migration versions that are NOT yet recorded in
    ``schema_migrations``. Lazily imported so the CI binary doesn't
    have to bring in asyncpg unless invoked."""
    import asyncpg  # type: ignore[import-not-found]

    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    backend = KnowledgeV2PostgresBackend(
        agent_id=None,
        dsn=dsn,
        schema=schema,
        embedding_dimension=embedding_dimension,
    )
    declared = [m.version for m in backend._migrations()]  # noqa: SLF001 — check-only path
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.execute(
            f"""CREATE TABLE IF NOT EXISTS "{schema}"."schema_migrations" (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
        )
        rows = await conn.fetch(f'SELECT version FROM "{schema}"."schema_migrations"')
    finally:
        await conn.close()
    applied = {str(row["version"]) for row in rows}
    return [version for version in declared if version not in applied]


def run(argv: Sequence[str] | None = None) -> int:
    """Apply migrations; return 0 on success, non-zero on failure.

    ``argv`` defaults to ``sys.argv[1:]`` minus the leading ``migrate``
    subcommand token, matching how :mod:`koda.__main__` dispatches.
    With ``--check`` the command instead lists pending versions and
    exits 3 if any are found — used by the CI gate to refuse a deploy
    whose code expects a schema that has not been rolled out yet.
    """
    setup_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)
    dsn = (args.dsn or "").strip()
    if not dsn:
        log.error("knowledge_v2_postgres_dsn_required")
        sys.stderr.write("error: KNOWLEDGE_V2_POSTGRES_DSN is empty; pass --dsn or set the env var.\n")
        return 2
    schema = (args.schema or "knowledge_v2").strip() or "knowledge_v2"
    if args.check:
        try:
            pending = asyncio.run(_pending_versions(dsn, schema, int(args.embedding_dimension)))
        except Exception:
            log.exception("knowledge_v2_migrate_check_failed")
            return 1
        if pending:
            log.warning("knowledge_v2_migrate_pending", schema=schema, count=len(pending))
            sys.stderr.write(f"pending migrations ({len(pending)}): {', '.join(pending)}\n")
            return 3
        log.info("knowledge_v2_migrate_check_clean", schema=schema)
        sys.stdout.write(f"no pending migrations (schema={schema})\n")
        return 0
    try:
        ok = asyncio.run(_apply(dsn, schema, int(args.embedding_dimension)))
    except Exception:
        log.exception("knowledge_v2_migrate_failed")
        return 1
    if not ok:
        log.error("knowledge_v2_migrate_returned_false", schema=schema)
        return 1
    log.info("knowledge_v2_migrate_applied", schema=schema)
    sys.stdout.write(f"migrations applied (schema={schema})\n")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
