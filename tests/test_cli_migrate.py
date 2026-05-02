"""``python -m koda migrate`` is the deterministic migration entry point.

The runtime ``bootstrap()`` path applies pending migrations on first
request as a defensive fallback. That fallback is not safe for fleet
deploys: every host racing the migration on first message produced the
019b regression that broke pause/activate. The fix is a CLI command CI
can run before rolling new code; these tests pin its contract.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.cli import migrate as migrate_cli


async def _async_return(value: Any) -> Any:
    return value


def test_run_returns_zero_on_success() -> None:
    fake_backend = MagicMock()
    fake_backend.bootstrap = AsyncMock(return_value=True)
    with (
        patch("koda.knowledge.v2.postgres_backend.KnowledgeV2PostgresBackend", return_value=fake_backend),
        patch.object(sys, "stdout"),
    ):
        rc = migrate_cli.run(["--dsn", "postgresql://user:pwd@h/db", "--schema", "knowledge_v2"])
    assert rc == 0
    fake_backend.bootstrap.assert_awaited_once()


def test_run_returns_one_when_bootstrap_returns_false() -> None:
    fake_backend = MagicMock()
    fake_backend.bootstrap = AsyncMock(return_value=False)
    with patch("koda.knowledge.v2.postgres_backend.KnowledgeV2PostgresBackend", return_value=fake_backend):
        rc = migrate_cli.run(["--dsn", "postgresql://user:pwd@h/db"])
    assert rc == 1


def test_run_returns_one_when_bootstrap_raises() -> None:
    fake_backend = MagicMock()
    fake_backend.bootstrap = AsyncMock(side_effect=RuntimeError("connection refused"))
    with patch("koda.knowledge.v2.postgres_backend.KnowledgeV2PostgresBackend", return_value=fake_backend):
        rc = migrate_cli.run(["--dsn", "postgresql://user:pwd@h/db"])
    assert rc == 1


def test_run_rejects_blank_dsn() -> None:
    """Without a DSN we cannot do anything useful — exit 2 (argparse-like
    misconfiguration) instead of silently no-oping."""
    with patch.object(migrate_cli, "KNOWLEDGE_V2_POSTGRES_DSN", ""):
        rc = migrate_cli.run([])
    assert rc == 2


def test_run_passes_schema_and_embedding_dimension_to_backend() -> None:
    """CLI flags must override env defaults for ad-hoc operator runs."""
    captured: dict[str, Any] = {}

    def _factory(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        backend = MagicMock()
        backend.bootstrap = AsyncMock(return_value=True)
        return backend

    with patch("koda.knowledge.v2.postgres_backend.KnowledgeV2PostgresBackend", side_effect=_factory):
        rc = migrate_cli.run(
            [
                "--dsn",
                "postgresql://user:pwd@h/db",
                "--schema",
                "ws_alpha",
                "--embedding-dimension",
                "768",
            ]
        )
    assert rc == 0
    assert captured["schema"] == "ws_alpha"
    assert captured["embedding_dimension"] == 768
    assert captured["dsn"] == "postgresql://user:pwd@h/db"


def test_check_flag_returns_zero_when_no_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2C — CI gate must exit 0 when the DSN is fully migrated
    so the deploy continues."""

    async def _no_pending(dsn: str, schema: str, dim: int) -> list[str]:
        return []

    monkeypatch.setattr(migrate_cli, "_pending_versions", _no_pending)
    rc = migrate_cli.run(["--dsn", "postgresql://h/db", "--check"])
    assert rc == 0


def test_check_flag_returns_three_when_pending_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pending migrations must block the deploy with a distinct exit
    code so the GitHub workflow can branch on it."""

    async def _pending(dsn: str, schema: str, dim: int) -> list[str]:
        return ["024_supervisor_cluster"]

    monkeypatch.setattr(migrate_cli, "_pending_versions", _pending)
    rc = migrate_cli.run(["--dsn", "postgresql://h/db", "--check"])
    assert rc == 3


def test_check_flag_returns_one_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any other failure (DSN unreachable, asyncpg missing) becomes
    an exit-1 — distinguishable from "pending exists" so CI can tell
    the operator the difference."""

    async def _explode(dsn: str, schema: str, dim: int) -> list[str]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(migrate_cli, "_pending_versions", _explode)
    rc = migrate_cli.run(["--dsn", "postgresql://h/db", "--check"])
    assert rc == 1


def test_main_dispatches_migrate_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    """``python -m koda migrate`` must hand off to ``koda.cli.migrate.run``
    before the runtime argparse fires (which would reject the positional
    ``migrate`` token)."""
    called: dict[str, Any] = {}

    def _fake_run(argv: list[str]) -> int:
        called["argv"] = list(argv)
        return 7

    monkeypatch.setattr(sys, "argv", ["koda", "migrate", "--schema", "ws_x"])
    monkeypatch.setattr("koda.cli.migrate.run", _fake_run)

    from koda import __main__ as main_mod

    with pytest.raises(SystemExit) as excinfo:
        main_mod.main()
    assert excinfo.value.code == 7
    assert called["argv"] == ["--schema", "ws_x"]
