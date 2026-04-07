"""Tests for db_manager: query validation, formatting, schema, explain, SSL, SSH, multi-env."""

import ssl
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.db_manager import DBManager, _EnvPool


@pytest.fixture
def _mock_asyncpg():
    """Ensure asyncpg is importable even when not installed."""
    mod = MagicMock()
    mod.create_pool = AsyncMock()
    prev = sys.modules.get("asyncpg")
    sys.modules["asyncpg"] = mod
    yield mod
    if prev is None:
        sys.modules.pop("asyncpg", None)
    else:
        sys.modules["asyncpg"] = prev


@pytest.fixture
def dbm():
    return DBManager()


def _setup_pool(dbm, mock_pool=None):
    """Helper to set up a single 'default' env pool for backward-compat tests."""
    if mock_pool is None:
        mock_pool = MagicMock()
    dbm._envs["default"] = _EnvPool(pool=mock_pool)
    return mock_pool


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_state(dbm):
    assert dbm.is_available is False
    assert dbm._envs == {}


# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------


class TestValidateQuery:
    def test_select_allowed(self, dbm):
        assert dbm._validate_query("SELECT 1") is None

    def test_select_with_whitespace(self, dbm):
        assert dbm._validate_query("  SELECT id FROM users") is None

    def test_with_select_allowed(self, dbm):
        assert dbm._validate_query("WITH cte AS (SELECT 1) SELECT * FROM cte") is None

    def test_show_allowed(self, dbm):
        assert dbm._validate_query("SHOW server_version") is None

    def test_explain_allowed(self, dbm):
        assert dbm._validate_query("EXPLAIN SELECT 1") is None

    def test_insert_blocked(self, dbm):
        result = dbm._validate_query("INSERT INTO users VALUES (1)")
        assert result is not None
        assert "blocked" in result.lower() or "Only SELECT" in result

    def test_update_blocked(self, dbm):
        result = dbm._validate_query("UPDATE users SET name = 'x'")
        assert result is not None

    def test_delete_blocked(self, dbm):
        result = dbm._validate_query("DELETE FROM users")
        assert result is not None

    def test_drop_blocked(self, dbm):
        result = dbm._validate_query("DROP TABLE users")
        assert result is not None

    def test_alter_blocked(self, dbm):
        result = dbm._validate_query("ALTER TABLE users ADD col int")
        assert result is not None

    def test_create_blocked(self, dbm):
        result = dbm._validate_query("CREATE TABLE foo (id int)")
        assert result is not None

    def test_truncate_blocked(self, dbm):
        result = dbm._validate_query("TRUNCATE users")
        assert result is not None

    def test_grant_blocked(self, dbm):
        result = dbm._validate_query("GRANT ALL ON users TO public")
        assert result is not None

    def test_copy_blocked(self, dbm):
        result = dbm._validate_query("COPY users TO '/tmp/out.csv'")
        assert result is not None

    def test_multistatement_blocked(self, dbm):
        result = dbm._validate_query("SELECT 1; DROP TABLE users")
        assert result is not None
        assert "Multi-statement" in result

    def test_comment_dash_blocked(self, dbm):
        result = dbm._validate_query("SELECT 1 -- comment")
        assert result is not None
        assert "comment" in result.lower()

    def test_comment_block_blocked(self, dbm):
        result = dbm._validate_query("SELECT /* */ 1")
        assert result is not None
        assert "comment" in result.lower()

    def test_backslash_blocked(self, dbm):
        result = dbm._validate_query("\\dt")
        assert result is not None
        assert "Backslash" in result

    def test_empty_query(self, dbm):
        result = dbm._validate_query("")
        assert result is not None
        assert "Empty" in result

    def test_select_with_blocked_subquery(self, dbm):
        # SELECT that contains a blocked keyword inside
        result = dbm._validate_query("SELECT * FROM (DELETE FROM users RETURNING *) sub")
        assert result is not None
        assert "blocked" in result.lower()


# ---------------------------------------------------------------------------
# Query execution and formatting
# ---------------------------------------------------------------------------


class TestQuery:
    @pytest.mark.asyncio
    async def test_query_not_available(self, dbm):
        result = await dbm.query("SELECT 1")
        assert "not available" in result or "No database pools" in result

    @pytest.mark.asyncio
    async def test_query_blocked_sql(self, dbm):
        _setup_pool(dbm)
        result = await dbm.query("DROP TABLE users")
        assert result.startswith("Error:")

    @pytest.mark.asyncio
    async def test_query_formats_table(self, dbm):
        mock_row1 = MagicMock()
        mock_row1.keys.return_value = ["id", "name"]
        mock_row1.__getitem__ = lambda self, k: {"id": 1, "name": "Alice"}[k]
        mock_row2 = MagicMock()
        mock_row2.keys.return_value = ["id", "name"]
        mock_row2.__getitem__ = lambda self, k: {"id": 2, "name": "Bob"}[k]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row1, mock_row2])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.query("SELECT id, name FROM users")
        assert "Rows: 2" in result
        assert "Alice" in result
        assert "Bob" in result
        assert "| id" in result
        assert "| name" in result

    @pytest.mark.asyncio
    async def test_query_truncates_rows(self, dbm):
        rows = []
        for i in range(150):
            row = MagicMock()
            row.keys.return_value = ["id"]
            row.__getitem__ = lambda self, k, val=i: val
            rows.append(row)

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.query("SELECT id FROM big_table", max_rows=100)
        assert "truncated" in result
        assert "50 more rows not shown" in result

    @pytest.mark.asyncio
    async def test_query_no_results(self, dbm):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.query("SELECT id FROM empty_table")
        assert "No results" in result
        assert "Rows: 0" in result


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSchema:
    @pytest.mark.asyncio
    async def test_schema_not_available(self, dbm):
        result = await dbm.get_schema()
        assert "not available" in result or "No database pools" in result

    @pytest.mark.asyncio
    async def test_schema_lists_tables(self, dbm):
        rows = [
            {"table_name": "users", "table_type": "BASE TABLE"},
            {"table_name": "orders", "table_type": "BASE TABLE"},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.get_schema()
        assert "users" in result
        assert "orders" in result
        assert "BASE TABLE" in result

    @pytest.mark.asyncio
    async def test_schema_forwards_custom_timeout(self, dbm):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.get_schema(timeout=17)
        assert "No tables found" in result
        assert mock_conn.fetch.await_args.kwargs["timeout"] == 17

    @pytest.mark.asyncio
    async def test_schema_shows_columns(self, dbm):
        rows = [
            {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None},
            {"column_name": "name", "data_type": "text", "is_nullable": "YES", "column_default": None},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=rows)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.get_schema("users")
        assert "id" in result
        assert "integer" in result
        assert "NOT NULL" in result
        assert "name" in result
        assert "text" in result

    @pytest.mark.asyncio
    async def test_schema_no_tables(self, dbm):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.get_schema()
        assert "No tables found" in result


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------


class TestExplain:
    @pytest.mark.asyncio
    async def test_explain_not_available(self, dbm):
        result = await dbm.explain("SELECT 1")
        assert "not available" in result or "No database pools" in result

    @pytest.mark.asyncio
    async def test_explain_blocks_non_select(self, dbm):
        _setup_pool(dbm)
        result = await dbm.explain("DELETE FROM users")
        assert "Error" in result
        assert "SELECT" in result

    @pytest.mark.asyncio
    async def test_explain_output(self, dbm):
        rows = [
            {"QUERY PLAN": "Seq Scan on users  (cost=0.00..1.04 rows=4 width=36)"},
        ]
        # asyncpg returns rows indexable by position
        mock_rows = []
        for row in rows:
            mock_row = MagicMock()
            mock_row.__getitem__ = MagicMock(side_effect=lambda i, r=row: list(r.values())[i])
            mock_rows.append(mock_row)

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.explain("SELECT * FROM users")
        assert "EXPLAIN:" in result
        assert "Seq Scan" in result

    @pytest.mark.asyncio
    async def test_explain_forwards_custom_timeout(self, dbm):
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value="Seq Scan on users")

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.explain("SELECT * FROM users", timeout=11)
        assert "EXPLAIN:" in result
        assert mock_conn.fetch.await_args.kwargs["timeout"] == 11

    @pytest.mark.asyncio
    async def test_explain_blocks_writable_cte(self, dbm):
        _setup_pool(dbm)
        result = await dbm.explain("WITH d AS (DELETE FROM users RETURNING *) SELECT * FROM d")
        assert "Error" in result
        assert "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_explain_analyze(self, dbm):
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value="Seq Scan on users (actual time=0.01..0.02 rows=4)")

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[mock_row])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        _setup_pool(dbm, mock_pool)

        result = await dbm.explain("SELECT * FROM users", analyze=True)
        assert "EXPLAIN ANALYZE:" in result


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_no_configs(self, dbm):
        with patch("koda.config.POSTGRES_ENV_CONFIGS", {}):
            await dbm.start()
        assert dbm.is_available is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, dbm):
        await dbm.stop()
        assert dbm.is_available is False

    @pytest.mark.asyncio
    async def test_stop_closes_pool(self, dbm):
        mock_pool = AsyncMock()
        dbm._envs["default"] = _EnvPool(pool=mock_pool)
        await dbm.stop()
        mock_pool.close.assert_awaited_once()
        assert dbm._envs == {}


# ---------------------------------------------------------------------------
# SSL
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    from koda.config import PostgresEnvConfig

    defaults = dict(
        url="postgresql://localhost/test",
        ssl_mode="disable",
        ssl_ca_cert="",
        ssl_client_cert="",
        ssl_client_key="",
        ssh_enabled=False,
        ssh_host="",
        ssh_port=22,
        ssh_user="",
        ssh_key_file="",
        ssh_password="",
    )
    defaults.update(overrides)
    return PostgresEnvConfig(**defaults)


class TestSSL:
    def test_ssl_disable_returns_none(self):
        config = _make_config(ssl_mode="disable")
        assert DBManager._build_ssl_context(config) is None

    def test_ssl_invalid_mode_raises(self):
        config = _make_config(ssl_mode="reqiure")
        with pytest.raises(ValueError, match="Unsupported ssl_mode"):
            DBManager._build_ssl_context(config)

    def test_ssl_require_verifies_peer_by_default(self):
        config = _make_config(ssl_mode="require")
        ctx = DBManager._build_ssl_context(config)
        assert ctx is not None
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_ssl_verify_ca_loads_ca(self):
        config = _make_config(ssl_mode="verify-ca", ssl_ca_cert="/tmp/ca.pem")
        with patch.object(ssl.SSLContext, "load_verify_locations") as mock_load:
            ctx = DBManager._build_ssl_context(config)
            assert ctx is not None
            assert ctx.check_hostname is False
            assert ctx.verify_mode == ssl.CERT_REQUIRED
            mock_load.assert_called_once_with("/tmp/ca.pem")

    def test_ssl_verify_full_checks_hostname(self):
        config = _make_config(ssl_mode="verify-full")
        ctx = DBManager._build_ssl_context(config)
        assert ctx is not None
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_ssl_client_cert_loaded(self):
        config = _make_config(
            ssl_mode="require",
            ssl_client_cert="/tmp/client.pem",
            ssl_client_key="/tmp/client.key",
        )
        with patch.object(ssl.SSLContext, "load_cert_chain") as mock_chain:
            ctx = DBManager._build_ssl_context(config)
            assert ctx is not None
            mock_chain.assert_called_once_with("/tmp/client.pem", "/tmp/client.key")


# ---------------------------------------------------------------------------
# SSH Tunnel
# ---------------------------------------------------------------------------


class TestSSHTunnel:
    @pytest.mark.asyncio
    async def test_ssh_tunnel_start(self):
        mock_listener = MagicMock()
        mock_listener.get_port.return_value = 54321

        mock_conn = AsyncMock()
        mock_conn.forward_local_port = AsyncMock(return_value=mock_listener)

        config = _make_config(
            ssh_enabled=True,
            ssh_host="bastion.example.com",
            ssh_port=22,
            ssh_user="deploy",
            ssh_key_file="/keys/id_rsa",
            ssh_password="",
        )

        mock_key = MagicMock()
        with (
            patch("asyncssh.connect", new_callable=AsyncMock, return_value=mock_conn) as mock_connect,
            patch.object(DBManager, "_read_ssh_key", return_value="fake-key-data") as mock_read,
            patch("asyncssh.import_private_key", return_value=mock_key) as mock_import,
        ):
            ssh_conn, ssh_listener, port = await DBManager._start_ssh_tunnel(config, "db.internal", 5432)
            assert port == 54321
            assert ssh_conn is mock_conn
            assert ssh_listener is mock_listener
            mock_read.assert_called_once_with("/keys/id_rsa")
            mock_import.assert_called_once_with("fake-key-data")
            mock_connect.assert_awaited_once()
            connect_kwargs = mock_connect.await_args.kwargs
            assert connect_kwargs["host"] == "bastion.example.com"
            assert connect_kwargs["port"] == 22
            assert connect_kwargs["username"] == "deploy"
            assert connect_kwargs["client_keys"] == [mock_key]
            assert "known_hosts" not in connect_kwargs
            mock_conn.forward_local_port.assert_awaited_once_with("127.0.0.1", 0, "db.internal", 5432)


# ---------------------------------------------------------------------------
# Integration: start with SSH / SSL
# ---------------------------------------------------------------------------


class TestStartIntegration:
    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_asyncpg")
    async def test_start_with_ssh_rewrites_dsn(self, dbm, _mock_asyncpg):
        mock_listener = MagicMock()
        mock_listener.get_port.return_value = 55555

        mock_ssh_conn = AsyncMock()
        mock_ssh_conn.forward_local_port = AsyncMock(return_value=mock_listener)

        mock_pool = AsyncMock()
        _mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        config = _make_config(
            url="postgresql://user:pass@db.remote:5432/mydb",
            ssh_enabled=True,
            ssh_host="bastion",
            ssh_port=22,
            ssh_user="deploy",
            ssh_key_file="",
            ssh_password="secret",
        )

        with (
            patch("koda.config.POSTGRES_ENV_CONFIGS", {"default": config}),
            patch("asyncssh.connect", new_callable=AsyncMock, return_value=mock_ssh_conn),
        ):
            await dbm.start()
            dsn_arg = _mock_asyncpg.create_pool.call_args[0][0]
            assert "127.0.0.1:55555" in dsn_arg
            assert "user:pass" in dsn_arg
            assert "mydb" in dsn_arg
            assert dbm.is_available

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_asyncpg")
    async def test_start_with_ssl_passes_context(self, dbm, _mock_asyncpg):
        mock_pool = AsyncMock()
        _mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        config = _make_config(
            url="postgresql://user@localhost:5432/mydb",
            ssl_mode="require",
        )

        with patch("koda.config.POSTGRES_ENV_CONFIGS", {"default": config}):
            await dbm.start()
            kwargs = _mock_asyncpg.create_pool.call_args[1]
            assert "ssl" in kwargs
            assert isinstance(kwargs["ssl"], ssl.SSLContext)
            assert dbm.is_available

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_asyncpg")
    async def test_start_with_ssh_no_credentials(self, dbm, _mock_asyncpg):
        mock_listener = MagicMock()
        mock_listener.get_port.return_value = 55555

        mock_ssh_conn = AsyncMock()
        mock_ssh_conn.forward_local_port = AsyncMock(return_value=mock_listener)

        mock_pool = AsyncMock()
        _mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        config = _make_config(
            url="postgresql://localhost:5432/mydb",
            ssh_enabled=True,
            ssh_host="bastion",
            ssh_port=22,
            ssh_user="deploy",
            ssh_key_file="",
            ssh_password="secret",
        )

        with (
            patch("koda.config.POSTGRES_ENV_CONFIGS", {"default": config}),
            patch("asyncssh.connect", new_callable=AsyncMock, return_value=mock_ssh_conn),
        ):
            await dbm.start()
            dsn_arg = _mock_asyncpg.create_pool.call_args[0][0]
            assert "127.0.0.1:55555" in dsn_arg
            assert "mydb" in dsn_arg

    @pytest.mark.asyncio
    async def test_start_ssh_failure_cleans_up(self, dbm):
        config = _make_config(
            url="postgresql://user@db:5432/mydb",
            ssh_enabled=True,
            ssh_host="bastion",
            ssh_port=22,
            ssh_user="deploy",
        )

        with (
            patch("koda.config.POSTGRES_ENV_CONFIGS", {"default": config}),
            patch("asyncssh.connect", new_callable=AsyncMock, side_effect=ConnectionRefusedError("refused")),
        ):
            await dbm.start()
            assert not dbm.is_available
            assert dbm._envs == {}

    @pytest.mark.asyncio
    async def test_stop_order_pool_then_tunnel(self, dbm):
        call_order = []

        mock_pool = AsyncMock()

        async def pool_close() -> None:
            call_order.append("pool_close")

        mock_pool.close = pool_close

        mock_listener = MagicMock()

        def listener_close() -> None:
            call_order.append("listener_close")

        mock_listener.close = listener_close

        mock_ssh_conn = AsyncMock()

        def ssh_close() -> None:
            call_order.append("ssh_close")

        mock_ssh_conn.close = ssh_close

        async def ssh_wait_closed() -> None:
            call_order.append("ssh_wait_closed")

        mock_ssh_conn.wait_closed = ssh_wait_closed

        dbm._envs["default"] = _EnvPool(pool=mock_pool, ssh_conn=mock_ssh_conn, ssh_listener=mock_listener)

        await dbm.stop()

        assert call_order == ["pool_close", "listener_close", "ssh_close", "ssh_wait_closed"]
        assert dbm._envs == {}


# ---------------------------------------------------------------------------
# Multi-env
# ---------------------------------------------------------------------------


class TestMultiEnv:
    def test_available_envs(self, dbm):
        dbm._envs["dev"] = _EnvPool(pool=MagicMock())
        dbm._envs["prod"] = _EnvPool(pool=MagicMock())
        assert set(dbm.available_envs) == {"dev", "prod"}

    def test_is_env_available(self, dbm):
        dbm._envs["prod"] = _EnvPool(pool=MagicMock())
        assert dbm.is_env_available("prod") is True
        assert dbm.is_env_available("dev") is False

    def test_get_pool_single_env(self, dbm):
        pool = MagicMock()
        dbm._envs["default"] = _EnvPool(pool=pool)
        env_name, p = dbm._get_pool()
        assert env_name == "default"
        assert p is pool

    def test_get_pool_multi_env_defaults_to_prod(self, dbm):
        dev_pool = MagicMock()
        prod_pool = MagicMock()
        dbm._envs["dev"] = _EnvPool(pool=dev_pool)
        dbm._envs["prod"] = _EnvPool(pool=prod_pool)
        env_name, p = dbm._get_pool()
        assert env_name == "prod"
        assert p is prod_pool

    def test_get_pool_explicit_env(self, dbm):
        dev_pool = MagicMock()
        prod_pool = MagicMock()
        dbm._envs["dev"] = _EnvPool(pool=dev_pool)
        dbm._envs["prod"] = _EnvPool(pool=prod_pool)
        env_name, p = dbm._get_pool("dev")
        assert env_name == "dev"
        assert p is dev_pool

    def test_get_pool_unknown_env_raises(self, dbm):
        dbm._envs["prod"] = _EnvPool(pool=MagicMock())
        with pytest.raises(ValueError, match="Unknown env"):
            dbm._get_pool("staging")

    def test_get_pool_no_pools_raises(self, dbm):
        with pytest.raises(ValueError, match="No database pools"):
            dbm._get_pool()

    @pytest.mark.asyncio
    async def test_query_with_env(self, dbm):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        dev_pool = MagicMock()
        dev_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        prod_pool = MagicMock()
        dbm._envs["dev"] = _EnvPool(pool=dev_pool)
        dbm._envs["prod"] = _EnvPool(pool=prod_pool)

        result = await dbm.query("SELECT 1", env="dev")
        assert "[dev]" in result
        dev_pool.acquire.assert_called()

    @pytest.mark.asyncio
    async def test_query_env_label_hidden_single(self, dbm):
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock(return_value=False)
            )
        )
        dbm._envs["default"] = _EnvPool(pool=mock_pool)

        result = await dbm.query("SELECT 1")
        assert "[default]" not in result

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("_mock_asyncpg")
    async def test_start_multi_env(self, dbm, _mock_asyncpg):
        mock_pool = AsyncMock()
        _mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)

        dev_config = _make_config(url="postgresql://localhost/dev")
        prod_config = _make_config(url="postgresql://localhost/prod")

        with patch("koda.config.POSTGRES_ENV_CONFIGS", {"dev": dev_config, "prod": prod_config}):
            await dbm.start()
            assert dbm.is_env_available("dev")
            assert dbm.is_env_available("prod")
            assert _mock_asyncpg.create_pool.call_count == 2


# ---------------------------------------------------------------------------
# SSH key format validation (SEC-9)
# ---------------------------------------------------------------------------


class TestReadSSHKeyValidation:
    @staticmethod
    def _private_key_fixture(label: str, body: str) -> str:
        return f"-----BEGIN {label}-----\n{body}\n-----END {label}-----\n"

    def test_valid_rsa_key(self, tmp_path):
        key_file = tmp_path / "id_rsa"
        key_file.write_text(self._private_key_fixture("RSA PRIVATE KEY", "MIIBogIBAAJ..."))
        result = DBManager._read_ssh_key(str(key_file))
        assert "BEGIN RSA PRIVATE KEY" in result

    def test_valid_ec_key(self, tmp_path):
        key_file = tmp_path / "id_ec"
        key_file.write_text(self._private_key_fixture("EC PRIVATE KEY", "MHQCAQEE..."))
        result = DBManager._read_ssh_key(str(key_file))
        assert "BEGIN EC PRIVATE KEY" in result

    def test_valid_openssh_key(self, tmp_path):
        key_file = tmp_path / "id_ed25519"
        key_file.write_text(self._private_key_fixture("OPENSSH PRIVATE KEY", "b3BlbnNza..."))
        result = DBManager._read_ssh_key(str(key_file))
        assert "BEGIN OPENSSH PRIVATE KEY" in result

    def test_valid_encrypted_key(self, tmp_path):
        key_file = tmp_path / "id_enc"
        key_file.write_text(self._private_key_fixture("ENCRYPTED PRIVATE KEY", "MIIFH..."))
        result = DBManager._read_ssh_key(str(key_file))
        assert "BEGIN ENCRYPTED PRIVATE KEY" in result

    def test_valid_generic_private_key(self, tmp_path):
        key_file = tmp_path / "id_generic"
        key_file.write_text(self._private_key_fixture("PRIVATE KEY", "MIIEvgI..."))
        result = DBManager._read_ssh_key(str(key_file))
        assert "BEGIN PRIVATE KEY" in result

    def test_public_key_rejected(self, tmp_path):
        key_file = tmp_path / "id_rsa.pub"
        key_file.write_text("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQ... user@host\n")
        with pytest.raises(ValueError, match="does not appear to contain a valid private key"):
            DBManager._read_ssh_key(str(key_file))

    def test_random_text_rejected(self, tmp_path):
        key_file = tmp_path / "not_a_key"
        key_file.write_text("this is not a key file at all\njust some random text\n")
        with pytest.raises(ValueError, match="does not appear to contain a valid private key"):
            DBManager._read_ssh_key(str(key_file))

    def test_empty_file_rejected(self, tmp_path):
        key_file = tmp_path / "empty"
        key_file.write_text("")
        with pytest.raises(ValueError, match="does not appear to contain a valid private key"):
            DBManager._read_ssh_key(str(key_file))
