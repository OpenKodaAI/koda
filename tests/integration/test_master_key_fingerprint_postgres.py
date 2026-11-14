"""AG-05 key-fingerprint matrix against a real Postgres (ADR-002 §2.5, §5.8, §5.9).

Pinned guarantees, through the production store and migration code:

  * Migration ``048_control_plane_master_key_fingerprint`` is additive and
    idempotent: it runs twice on a fresh schema, creates only the
    fingerprint table, and dropping that table (its reversal) leaves the
    rest of the schema working; a later bootstrap recreates it.
  * Fresh install: the key file and the fingerprint row are created; the row
    holds an HMAC, never the key.
  * Upgrade: an install with a key and ciphertext but no fingerprint row
    records the fingerprint from the present key; the ciphertext row is
    byte-identical afterwards and still decrypts.
  * Mismatch, or a missing key while a fingerprint or ciphertext exists,
    refuses startup and creates no key file.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest
from cryptography.fernet import Fernet

from koda.control_plane import crypto

pytestmark = [pytest.mark.postgres]

_SCHEMA = os.environ.get("KNOWLEDGE_V2_POSTGRES_SCHEMA") or "knowledge_v2"
_MIGRATION = "048_control_plane_master_key_fingerprint"
# Every table the bootstrap treats as holding ciphertext, plus the fingerprint.
_KEY_TABLES = (
    "cp_master_key_fingerprint",
    "cp_secret_values",
    "cp_mcp_oauth_tokens",
    "cp_mcp_agent_connections",
    "cp_provider_login_sessions",
    "cp_agent_config_versions",
)


async def _query(dsn: str, sql: str, *params: Any) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetch(sql, *params)
    finally:
        await conn.close()


async def _clear_key_tables(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    try:
        for table in _KEY_TABLES:
            await conn.execute(f'DELETE FROM "{_SCHEMA}"."{table}"')
        await conn.execute(
            f"""DELETE FROM "{_SCHEMA}"."audit_events" WHERE event_type = 'security.master_key_fingerprint_recorded'"""
        )
    finally:
        await conn.close()


@pytest.fixture
async def key_db(
    migrated_postgres: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[SimpleNamespace]:
    from koda.knowledge.v2 import common as common_mod

    common_mod._SHARED_POSTGRES_BACKENDS.clear()
    await _clear_key_tables(migrated_postgres)
    key_file = tmp_path / "state" / "control_plane" / ".master.key"
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY", "")
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_FILE", key_file)
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_PREVIOUS", "")
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE", tmp_path / "none" / ".previous.key")
    crypto.clear_fernet_cache()
    try:
        yield SimpleNamespace(dsn=migrated_postgres, key_file=key_file)
    finally:
        crypto.clear_fernet_cache()
        await _clear_key_tables(migrated_postgres)
        common_mod._SHARED_POSTGRES_BACKENDS.clear()


async def _fingerprint_rows(dsn: str) -> list[asyncpg.Record]:
    return await _query(dsn, f'SELECT * FROM "{_SCHEMA}"."cp_master_key_fingerprint"')


async def _insert_secret(dsn: str, ciphertext: str) -> None:
    await _query(
        dsn,
        f"""INSERT INTO "{_SCHEMA}"."cp_secret_values"
               (scope_id, agent_id, secret_key, encrypted_value, preview, created_at, updated_at)
            VALUES ('global', NULL, 'AG05_TEST_SECRET', $1, 'se****et', 'now', 'now')""",
        ciphertext,
    )


async def test_migration_runs_twice_and_its_reversal_is_safe(migrated_postgres: str) -> None:
    from koda.knowledge.v2.postgres_backend import KnowledgeV2PostgresBackend

    schema = f"ag05_mk_{uuid.uuid4().hex[:8]}"

    def _backend() -> KnowledgeV2PostgresBackend:
        return KnowledgeV2PostgresBackend(agent_id=None, dsn=migrated_postgres, schema=schema, embedding_dimension=8)

    try:
        assert await _backend().bootstrap() is True
        assert await _backend().bootstrap() is True

        columns = await _query(
            migrated_postgres,
            """SELECT column_name FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = 'cp_master_key_fingerprint'
                ORDER BY ordinal_position""",
            schema,
        )
        assert [row["column_name"] for row in columns] == [
            "key_name",
            "fingerprint",
            "recorded_reason",
            "created_at",
            "updated_at",
        ]
        applied = await _query(
            migrated_postgres, f'SELECT version FROM "{schema}"."schema_migrations" WHERE version = $1', _MIGRATION
        )
        assert len(applied) == 1

        # Reversal: drop the table and forget the migration; the next
        # bootstrap recreates it and nothing else depends on it.
        await _query(migrated_postgres, f'DROP TABLE "{schema}"."cp_master_key_fingerprint"')
        await _query(migrated_postgres, f'DELETE FROM "{schema}"."schema_migrations" WHERE version = $1', _MIGRATION)
        assert await _backend().bootstrap() is True
        recreated = await _query(
            migrated_postgres,
            """SELECT 1 FROM information_schema.tables
                WHERE table_schema = $1 AND table_name = 'cp_master_key_fingerprint'""",
            schema,
        )
        assert len(recreated) == 1
    finally:
        await _query(migrated_postgres, f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


async def test_fresh_install_then_restart(key_db: SimpleNamespace) -> None:
    assert crypto.ensure_master_key() == "fresh_install"

    key = key_db.key_file.read_bytes().strip()
    rows = await _fingerprint_rows(key_db.dsn)
    assert len(rows) == 1
    assert rows[0]["key_name"] == "control_plane_master_key"
    assert rows[0]["fingerprint"] == crypto.master_key_fingerprint(key)
    assert rows[0]["recorded_reason"] == "fresh_install"
    assert key.decode() not in str(dict(rows[0]))
    audit = await _query(
        key_db.dsn,
        f"""SELECT details_json::text AS details FROM "{_SCHEMA}"."audit_events"
             WHERE event_type = 'security.master_key_fingerprint_recorded'""",
    )
    assert len(audit) == 1
    assert "fresh_install" in audit[0]["details"]
    assert key.decode() not in audit[0]["details"]

    assert crypto.ensure_master_key() == "verified"
    assert key_db.key_file.read_bytes().strip() == key
    assert await _fingerprint_rows(key_db.dsn) == rows


async def test_existing_install_upgrades_without_touching_ciphertext(key_db: SimpleNamespace) -> None:
    key = Fernet.generate_key()
    key_db.key_file.parent.mkdir(parents=True)
    key_db.key_file.write_bytes(key)
    key_db.key_file.chmod(0o600)
    ciphertext = Fernet(key).encrypt(b"pre-upgrade-secret").decode()
    await _insert_secret(key_db.dsn, ciphertext)

    assert crypto.ensure_master_key() == "upgrade"

    rows = await _fingerprint_rows(key_db.dsn)
    assert [(row["fingerprint"], row["recorded_reason"]) for row in rows] == [
        (crypto.master_key_fingerprint(key), "upgrade")
    ]
    stored = await _query(
        key_db.dsn,
        f"""SELECT encrypted_value FROM "{_SCHEMA}"."cp_secret_values" WHERE secret_key = 'AG05_TEST_SECRET'""",
    )
    assert [row["encrypted_value"] for row in stored] == [ciphertext]
    assert crypto.decrypt_secret(ciphertext) == "pre-upgrade-secret"
    assert key_db.key_file.read_bytes() == key


async def test_missing_key_while_secrets_exist_refuses(key_db: SimpleNamespace) -> None:
    await _insert_secret(key_db.dsn, Fernet(Fernet.generate_key()).encrypt(b"orphan").decode())

    with pytest.raises(crypto.MasterKeyUnavailable, match="encrypted secrets"):
        crypto.ensure_master_key()

    assert not key_db.key_file.exists()
    assert await _fingerprint_rows(key_db.dsn) == []


@pytest.mark.parametrize(
    "seed_sql",
    [
        """INSERT INTO "{schema}"."cp_mcp_oauth_tokens" (agent_id, server_key, access_token_encrypted)
           VALUES ('AGENT_A', 'srv', 'gAAAA-ciphertext')""",
        """INSERT INTO "{schema}"."cp_mcp_agent_connections"
               (agent_id, server_key, env_values_json, created_at, updated_at)
           VALUES ('AGENT_A', 'srv', '{{"TOKEN": "gAAAA-ciphertext"}}', 'now', 'now')""",
        """INSERT INTO "{schema}"."cp_provider_login_sessions" (id, provider_id, details_json, created_at, updated_at)
           VALUES ('sess', 'claude', '{{"encrypted_details": "gAAAA-ciphertext"}}', 'now', 'now')""",
        """INSERT INTO "{schema}"."cp_agent_config_versions"
               (agent_id, version, snapshot_json, created_at, published_at)
           VALUES ('AGENT_A', 1, '{{"secrets": {{"K": {{"encrypted_value": "gAAAA"}}}}}}', 'now', 'now')""",
    ],
    ids=["mcp_oauth_tokens", "mcp_connection_env", "provider_login_session", "published_snapshot"],
)
async def test_every_ciphertext_store_blocks_key_generation(key_db: SimpleNamespace, seed_sql: str) -> None:
    await _query(key_db.dsn, seed_sql.format(schema=_SCHEMA))

    with pytest.raises(crypto.MasterKeyUnavailable, match="encrypted secrets"):
        crypto.ensure_master_key()

    assert not key_db.key_file.exists()


async def test_empty_connection_env_does_not_count_as_ciphertext(key_db: SimpleNamespace) -> None:
    await _query(
        key_db.dsn,
        f"""INSERT INTO "{_SCHEMA}"."cp_mcp_agent_connections"
               (agent_id, server_key, env_values_json, created_at, updated_at)
            VALUES ('AGENT_A', 'srv', '{{}}', 'now', 'now')""",
    )

    assert crypto.ensure_master_key() == "fresh_install"


async def test_mismatch_and_lost_key_refuse_after_fingerprint(key_db: SimpleNamespace) -> None:
    crypto.ensure_master_key()
    recorded = await _fingerprint_rows(key_db.dsn)

    other = Fernet.generate_key()
    key_db.key_file.write_bytes(other)
    with pytest.raises(crypto.MasterKeyMismatch):
        crypto.ensure_master_key()
    assert key_db.key_file.read_bytes() == other

    key_db.key_file.unlink()
    with pytest.raises(crypto.MasterKeyUnavailable, match="fingerprint"):
        crypto.ensure_master_key()
    assert not key_db.key_file.exists()
    assert await _fingerprint_rows(key_db.dsn) == recorded


async def test_rotation_rerecords_fingerprint_in_postgres(
    key_db: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crypto.ensure_master_key()
    old_key = key_db.key_file.read_bytes().strip()
    previous_file = tmp_path / "state" / "control_plane" / ".master-previous.key"
    previous_file.write_bytes(old_key)
    new_key = Fernet.generate_key()
    key_db.key_file.write_bytes(new_key)
    monkeypatch.setattr(crypto, "CONTROL_PLANE_MASTER_KEY_PREVIOUS_FILE", previous_file)
    crypto.clear_fernet_cache()

    assert crypto.ensure_master_key() == "rotation"

    rows = await _fingerprint_rows(key_db.dsn)
    assert [(row["fingerprint"], row["recorded_reason"]) for row in rows] == [
        (crypto.master_key_fingerprint(new_key), "rotation")
    ]
    assert crypto.ensure_master_key() == "verified"
