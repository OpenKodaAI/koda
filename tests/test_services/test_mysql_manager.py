"""Tests for MySQL manager and tool handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from koda.services.mysql_manager import MySQLManager, _validate_query
from koda.services.tool_dispatcher import ToolContext


def _make_ctx(**overrides: object) -> ToolContext:
    defaults: dict = {
        "user_id": 1,
        "chat_id": 1,
        "work_dir": "/tmp",
        "user_data": {
            "work_dir": "/tmp",
            "model": "m",
            "session_id": "s",
            "total_cost": 0.0,
            "query_count": 0,
        },
        "agent": AsyncMock(),
        "agent_mode": "autonomous",
    }
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestMySQLValidation:
    def test_valid_select(self) -> None:
        assert _validate_query("SELECT * FROM users") == ""

    def test_valid_show(self) -> None:
        assert _validate_query("SHOW TABLES") == ""

    def test_valid_describe(self) -> None:
        assert _validate_query("DESCRIBE users") == ""

    def test_valid_explain(self) -> None:
        assert _validate_query("EXPLAIN SELECT 1") == ""

    def test_block_insert(self) -> None:
        assert _validate_query("INSERT INTO users VALUES(1)") != ""

    def test_block_drop(self) -> None:
        assert _validate_query("DROP TABLE users") != ""

    def test_block_update(self) -> None:
        assert _validate_query("UPDATE users SET name='x'") != ""

    def test_block_delete(self) -> None:
        assert _validate_query("DELETE FROM users") != ""

    def test_block_truncate(self) -> None:
        assert _validate_query("TRUNCATE TABLE users") != ""

    def test_empty(self) -> None:
        assert _validate_query("") != ""

    def test_block_comments_dash(self) -> None:
        assert _validate_query("SELECT 1 -- comment") != ""

    def test_block_comments_block(self) -> None:
        assert _validate_query("SELECT /* hack */ 1") != ""

    def test_block_multi_statement(self) -> None:
        assert _validate_query("SELECT 1; DROP TABLE users") != ""

    def test_block_unknown_keyword(self) -> None:
        assert _validate_query("CALL my_proc()") != ""


class TestMySQLManager:
    @pytest.mark.asyncio
    async def test_start_without_aiomysql(self) -> None:
        manager = MySQLManager()
        _real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "aiomysql":
                raise ImportError("no aiomysql")
            return _real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_fake_import):
            await manager.start()
        assert not manager.is_available

    @pytest.mark.asyncio
    async def test_query_validation_error(self) -> None:
        manager = MySQLManager()
        manager._available = True
        result = await manager.query("DROP TABLE users")
        assert result.startswith("Error")

    @pytest.mark.asyncio
    async def test_query_empty(self) -> None:
        manager = MySQLManager()
        manager._available = True
        result = await manager.query("")
        assert result.startswith("Error")


class TestMySQLHandlers:
    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        from koda.services.tool_dispatcher import _handle_mysql_query

        with patch("koda.services.tool_dispatcher.MYSQL_ENABLED", False):
            result = await _handle_mysql_query({"sql": "SELECT 1"}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_missing_sql(self) -> None:
        from koda.services.tool_dispatcher import _handle_mysql_query

        with patch("koda.services.tool_dispatcher.MYSQL_ENABLED", True):
            result = await _handle_mysql_query({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_unavailable_manager(self) -> None:
        from koda.services.tool_dispatcher import _handle_mysql_query

        mock_manager = MySQLManager()
        mock_manager._available = False
        with (
            patch("koda.services.tool_dispatcher.MYSQL_ENABLED", True),
            patch("koda.services.mysql_manager.get_mysql_manager", return_value=mock_manager),
        ):
            result = await _handle_mysql_query({"sql": "SELECT 1"}, _make_ctx())
        assert not result.success
        assert "not available" in result.output

    @pytest.mark.asyncio
    async def test_schema_disabled(self) -> None:
        from koda.services.tool_dispatcher import _handle_mysql_schema

        with patch("koda.services.tool_dispatcher.MYSQL_ENABLED", False):
            result = await _handle_mysql_schema({}, _make_ctx())
        assert not result.success

    @pytest.mark.asyncio
    async def test_schema_unavailable(self) -> None:
        from koda.services.tool_dispatcher import _handle_mysql_schema

        mock_manager = MySQLManager()
        mock_manager._available = False
        with (
            patch("koda.services.tool_dispatcher.MYSQL_ENABLED", True),
            patch("koda.services.mysql_manager.get_mysql_manager", return_value=mock_manager),
        ):
            result = await _handle_mysql_schema({}, _make_ctx())
        assert not result.success


class TestMySQLPrompt:
    def test_section_is_not_advertised(self) -> None:
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "mysql_query" not in prompt
        assert "### MySQL" not in prompt
