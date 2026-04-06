"""Tests for database write tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides) -> ToolContext:
    defaults = dict(
        user_id=1,
        chat_id=1,
        work_dir="/tmp",
        user_data={
            "work_dir": "/tmp",
            "model": "m",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
            "postgres_env": "dev",
        },
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


# ---------------------------------------------------------------------------
# Write query validation
# ---------------------------------------------------------------------------


class TestWriteValidation:
    def test_validate_insert(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("INSERT INTO users (name) VALUES ('Alice')") == ""

    def test_validate_update(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("UPDATE users SET active = true WHERE id = 1") == ""

    def test_validate_delete(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("DELETE FROM sessions WHERE expires_at < now()") == ""

    def test_block_select(self):
        from koda.services.db_manager import _validate_write_query

        assert "INSERT, UPDATE, DELETE" in _validate_write_query("SELECT * FROM users")

    def test_block_drop(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("DROP TABLE users")
        assert result != ""

    def test_block_alter(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("ALTER TABLE users ADD COLUMN age int")
        assert result != ""

    def test_block_truncate(self):
        from koda.services.db_manager import _validate_write_query

        result = _validate_write_query("TRUNCATE TABLE users")
        assert result != ""

    def test_block_ddl_keyword_in_write(self):
        from koda.services.db_manager import _validate_write_query

        # DDL keyword embedded in an otherwise valid-looking write
        assert "DDL" in _validate_write_query("DELETE FROM users WHERE name = 'DROP TABLE test'")

    def test_block_multi_statement(self):
        from koda.services.db_manager import _validate_write_query

        assert "Multi-statement" in _validate_write_query("DELETE FROM a; DELETE FROM b")

    def test_allow_trailing_semicolon(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("INSERT INTO users (name) VALUES ('x');") == ""

    def test_block_comments_dashes(self):
        from koda.services.db_manager import _validate_write_query

        assert "comments" in _validate_write_query("DELETE FROM users -- all of them")

    def test_block_comments_block(self):
        from koda.services.db_manager import _validate_write_query

        assert "comments" in _validate_write_query("DELETE FROM users /* danger */")

    def test_empty_sql(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("") != ""

    def test_whitespace_only(self):
        from koda.services.db_manager import _validate_write_query

        assert _validate_write_query("   ") != ""


# ---------------------------------------------------------------------------
# WHERE clause enforcement
# ---------------------------------------------------------------------------


class TestWhereRequired:
    def test_update_without_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("UPDATE users SET active = false") is not None

    def test_update_with_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("UPDATE users SET active = false WHERE id = 1") is None

    def test_delete_without_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("DELETE FROM users") is not None

    def test_delete_with_where(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("DELETE FROM users WHERE id = 1") is None

    def test_insert_no_where_needed(self):
        from koda.services.db_manager import _check_where_required

        assert _check_where_required("INSERT INTO users (name) VALUES ('x')") is None


# ---------------------------------------------------------------------------
# Affected rows parsing
# ---------------------------------------------------------------------------


class TestParseAffectedRows:
    def test_insert(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("INSERT 0 5") == 5

    def test_update(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("UPDATE 3") == 3

    def test_delete(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("DELETE 2") == 2

    def test_none(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows(None) == 0

    def test_empty(self):
        from koda.services.db_manager import _parse_affected_rows

        assert _parse_affected_rows("") == 0


# ---------------------------------------------------------------------------
# db_execute handler
# ---------------------------------------------------------------------------


class TestDbExecuteHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_db_execute

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", False),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
        ):
            result = await _handle_db_execute({"sql": "INSERT INTO x VALUES(1)"}, _make_ctx())
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_db_not_enabled(self):
        from koda.services.tool_dispatcher import _handle_db_execute

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", False),
        ):
            result = await _handle_db_execute({"sql": "INSERT INTO x VALUES(1)"}, _make_ctx())
        assert not result.success
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_missing_sql(self):
        from koda.services.tool_dispatcher import _handle_db_execute

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
        ):
            result = await _handle_db_execute({}, _make_ctx())
        assert not result.success
        assert "sql" in result.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_db_execute

        mock_manager = MagicMock()
        mock_manager.execute_write = AsyncMock(
            return_value={
                "success": True,
                "affected_rows": 1,
                "command": "INSERT 0 1",
                "env": "dev",
                "plan": "",
            }
        )
        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
            patch("koda.services.db_manager.db_manager", mock_manager),
        ):
            result = await _handle_db_execute({"sql": "INSERT INTO users (name) VALUES ('Alice')"}, _make_ctx())
        assert result.success
        assert "1" in result.output

    @pytest.mark.asyncio
    async def test_error_from_manager(self):
        from koda.services.tool_dispatcher import _handle_db_execute

        mock_manager = MagicMock()
        mock_manager.execute_write = AsyncMock(return_value={"error": "Write not allowed on 'prod'."})
        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
            patch("koda.services.db_manager.db_manager", mock_manager),
        ):
            result = await _handle_db_execute({"sql": "INSERT INTO x VALUES(1)"}, _make_ctx())
        assert not result.success
        assert "prod" in result.output


# ---------------------------------------------------------------------------
# db_execute_plan handler
# ---------------------------------------------------------------------------


class TestDbExecutePlanHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_db_execute_plan

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", False),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
        ):
            result = await _handle_db_execute_plan({"sql": "UPDATE x SET a=1 WHERE id=1"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_db_execute_plan

        mock_manager = MagicMock()
        mock_manager.explain_write = AsyncMock(return_value={"success": True, "plan": "Seq Scan on x", "env": "dev"})
        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
            patch("koda.services.db_manager.db_manager", mock_manager),
        ):
            result = await _handle_db_execute_plan({"sql": "UPDATE x SET a=1 WHERE id=1"}, _make_ctx())
        assert result.success
        assert "Seq Scan" in result.output


# ---------------------------------------------------------------------------
# db_transaction handler
# ---------------------------------------------------------------------------


class TestDbTransactionHandler:
    @pytest.mark.asyncio
    async def test_disabled(self):
        from koda.services.tool_dispatcher import _handle_db_transaction

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", False),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
        ):
            result = await _handle_db_transaction({"statements": [{"sql": "INSERT INTO x VALUES(1)"}]}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_statements(self):
        from koda.services.tool_dispatcher import _handle_db_transaction

        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
        ):
            result = await _handle_db_transaction({}, _make_ctx())
        assert not result.success
        assert "statements" in result.output.lower()

    @pytest.mark.asyncio
    async def test_success(self):
        from koda.services.tool_dispatcher import _handle_db_transaction

        mock_manager = MagicMock()
        mock_manager.execute_transaction = AsyncMock(
            return_value={
                "success": True,
                "results": [
                    {"sql": "INSERT INTO x VALUES(1)", "affected_rows": 1, "command": "INSERT 0 1"},
                    {"sql": "UPDATE x SET a=2 WHERE id=1", "affected_rows": 1, "command": "UPDATE 1"},
                ],
                "total_affected_rows": 2,
                "env": "dev",
            }
        )
        with (
            patch("koda.services.tool_dispatcher.POSTGRES_WRITE_ENABLED", True),
            patch("koda.services.tool_dispatcher.POSTGRES_ENABLED", True),
            patch("koda.services.db_manager.db_manager", mock_manager),
        ):
            result = await _handle_db_transaction(
                {"statements": [{"sql": "INSERT INTO x VALUES(1)"}, {"sql": "UPDATE x SET a=2 WHERE id=1"}]},
                _make_ctx(),
            )
        assert result.success
        assert "2" in result.output


# ---------------------------------------------------------------------------
# Tool prompt
# ---------------------------------------------------------------------------


class TestDbWritePrompt:
    def test_write_section_is_not_advertised(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "Database Write" not in prompt
        assert "db_execute" not in prompt
