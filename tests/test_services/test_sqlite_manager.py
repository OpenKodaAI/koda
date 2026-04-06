"""Tests for sqlite_manager: query validation, path validation, schema, handlers, and prompt."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.sqlite_manager import (
    SQLiteManager,
    _validate_db_path,
    _validate_query,
    get_sqlite_manager,
)

# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------


class TestValidateQuery:
    def test_select_allowed(self):
        assert _validate_query("SELECT 1") == ""

    def test_select_with_whitespace(self):
        assert _validate_query("  SELECT id FROM users") == ""

    def test_pragma_allowed(self):
        assert _validate_query("PRAGMA table_info('users')") == ""

    def test_empty_query(self):
        assert _validate_query("") == "Empty SQL."
        assert _validate_query("   ") == "Empty SQL."

    def test_insert_blocked(self):
        result = _validate_query("INSERT INTO users VALUES (1)")
        assert "Write operations" in result

    def test_update_blocked(self):
        result = _validate_query("UPDATE users SET name='x'")
        assert "Write operations" in result

    def test_delete_blocked(self):
        result = _validate_query("DELETE FROM users")
        assert "Write operations" in result

    def test_drop_blocked(self):
        result = _validate_query("DROP TABLE users")
        assert "Write operations" in result

    def test_create_blocked(self):
        result = _validate_query("CREATE TABLE t(id INT)")
        assert "Write operations" in result

    def test_comments_blocked(self):
        assert "comment" in _validate_query("SELECT 1 -- test").lower()
        assert "comment" in _validate_query("SELECT /* test */ 1").lower()

    def test_multi_statement_blocked(self):
        result = _validate_query("SELECT 1; DROP TABLE users")
        assert "Multi-statement" in result

    def test_backslash_blocked(self):
        result = _validate_query("SELECT \\dt")
        assert "Backslash" in result

    def test_unknown_leading_keyword(self):
        result = _validate_query("ATTACH DATABASE 'foo.db' AS foo")
        assert "Only SELECT and PRAGMA" in result


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


class TestValidateDbPath:
    def test_empty_path(self):
        assert _validate_db_path("") == "Missing db_path."

    def test_nonexistent_file(self):
        result = _validate_db_path("/nonexistent/db.sqlite")
        assert result is not None
        assert "not found" in result

    def test_valid_file_no_allowed_paths(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
                assert _validate_db_path(path) is None
        finally:
            os.unlink(path)

    def test_file_in_allowed_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with open(db_path, "w") as f:
                f.write("")
            with patch("koda.config.SQLITE_ALLOWED_PATHS", [tmpdir]):
                assert _validate_db_path(db_path) is None

    def test_file_not_in_allowed_path(self):
        with tempfile.TemporaryDirectory() as allowed_dir, tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            f.write(b"")
            path = f.name
        try:
            with patch("koda.config.SQLITE_ALLOWED_PATHS", [allowed_dir]):
                result = _validate_db_path(path)
                assert result is not None
                assert "not in allowed" in result
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Manager basics
# ---------------------------------------------------------------------------


class TestSQLiteManager:
    @pytest.fixture
    def mgr(self):
        return SQLiteManager()

    def test_initial_state(self, mgr):
        assert mgr.is_available is False

    @pytest.mark.asyncio
    async def test_start_with_aiosqlite(self, mgr):
        """When aiosqlite is importable, manager becomes available."""
        await mgr.start()
        # In CI aiosqlite may or may not be installed; test the logic path
        try:
            import aiosqlite  # noqa: F401

            assert mgr.is_available is True
        except ImportError:
            assert mgr.is_available is False

    @pytest.mark.asyncio
    async def test_stop_is_noop(self, mgr):
        await mgr.stop()  # Should not raise


# ---------------------------------------------------------------------------
# Query and schema with real SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_db():
    """Create a temporary SQLite database with sample data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com')")
    conn.commit()
    conn.close()
    yield db_path
    os.unlink(db_path)


@pytest.mark.asyncio
async def test_query_success(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
        result = await mgr.query("SELECT name FROM users ORDER BY id", sample_db)
    assert "Alice" in result
    assert "Bob" in result
    assert "(2 rows)" in result


@pytest.mark.asyncio
async def test_query_max_rows(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
        result = await mgr.query("SELECT name FROM users ORDER BY id", sample_db, max_rows=1)
    assert "Alice" in result
    assert "(1 rows)" in result


@pytest.mark.asyncio
async def test_query_validation_error(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    result = await mgr.query("INSERT INTO users VALUES (3, 'Eve', 'e@e.com')", sample_db)
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_query_path_error():
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    result = await mgr.query("SELECT 1", "/nonexistent/db.sqlite")
    assert result.startswith("Error")


@pytest.mark.asyncio
async def test_schema_list_tables(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
        result = await mgr.get_schema(sample_db)
    assert "users" in result
    assert "Tables (1)" in result


@pytest.mark.asyncio
async def test_schema_table_columns(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
        result = await mgr.get_schema(sample_db, table="users")
    assert "Table: users" in result
    assert "name" in result
    assert "email" in result


@pytest.mark.asyncio
async def test_schema_nonexistent_table(sample_db):
    pytest.importorskip("aiosqlite")
    mgr = SQLiteManager()
    await mgr.start()
    with patch("koda.config.SQLITE_ALLOWED_PATHS", []):
        result = await mgr.get_schema(sample_db, table="nonexistent")
    assert "not found" in result


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_sqlite_manager_returns_same_instance():
    import koda.services.sqlite_manager as mod

    old = mod._manager
    mod._manager = None
    try:
        m1 = get_sqlite_manager()
        m2 = get_sqlite_manager()
        assert m1 is m2
    finally:
        mod._manager = old


# ---------------------------------------------------------------------------
# Dispatcher handler tests
# ---------------------------------------------------------------------------


class TestHandlerSqliteQuery:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_sqlite_query

        with patch("koda.services.tool_dispatcher.SQLITE_ENABLED", False):
            ctx = AsyncMock()
            result = await _handle_sqlite_query({}, ctx)
            assert result.success is False
            assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_missing_params(self):
        from koda.services.tool_dispatcher import _handle_sqlite_query

        with patch("koda.services.tool_dispatcher.SQLITE_ENABLED", True):
            ctx = AsyncMock()
            result = await _handle_sqlite_query({"sql": "SELECT 1"}, ctx)
            assert result.success is False
            assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_bad_max_rows(self):
        from koda.services.tool_dispatcher import _handle_sqlite_query

        with patch("koda.services.tool_dispatcher.SQLITE_ENABLED", True):
            ctx = AsyncMock()
            result = await _handle_sqlite_query({"sql": "SELECT 1", "db_path": "/tmp/x.db", "max_rows": "abc"}, ctx)
            assert result.success is False
            assert "max_rows" in result.output


class TestHandlerSqliteSchema:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_sqlite_schema

        with patch("koda.services.tool_dispatcher.SQLITE_ENABLED", False):
            ctx = AsyncMock()
            result = await _handle_sqlite_schema({}, ctx)
            assert result.success is False
            assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_missing_db_path(self):
        from koda.services.tool_dispatcher import _handle_sqlite_schema

        with patch("koda.services.tool_dispatcher.SQLITE_ENABLED", True):
            ctx = AsyncMock()
            result = await _handle_sqlite_schema({}, ctx)
            assert result.success is False
            assert "Missing" in result.output


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


class TestToolPromptSQLite:
    def test_sqlite_prompt_is_not_advertised(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "sqlite_query" not in prompt
        assert "sqlite_schema" not in prompt
        assert "### SQLite" not in prompt
