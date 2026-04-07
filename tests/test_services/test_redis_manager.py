"""Tests for the Redis read-only manager and redis_query tool handler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from koda.services.redis_manager import READ_ONLY_COMMANDS, RedisManager, get_redis_manager

# ---------------------------------------------------------------------------
# Whitelist tests
# ---------------------------------------------------------------------------


def test_read_only_commands_allows_get() -> None:
    assert "GET" in READ_ONLY_COMMANDS


def test_read_only_commands_blocks_set() -> None:
    assert "SET" not in READ_ONLY_COMMANDS


def test_read_only_commands_blocks_del() -> None:
    assert "DEL" not in READ_ONLY_COMMANDS


def test_read_only_commands_blocks_flushdb() -> None:
    assert "FLUSHDB" not in READ_ONLY_COMMANDS


def test_read_only_commands_blocks_flushall() -> None:
    assert "FLUSHALL" not in READ_ONLY_COMMANDS


@pytest.mark.asyncio
async def test_execute_blocks_write_command() -> None:
    mgr = RedisManager()
    mgr._available = True
    result = await mgr.execute("SET", ["key", "value"])
    assert result.startswith("Error: command 'SET' is not allowed.")


@pytest.mark.asyncio
async def test_execute_blocks_del_command() -> None:
    mgr = RedisManager()
    mgr._available = True
    result = await mgr.execute("DEL", ["key"])
    assert result.startswith("Error: command 'DEL' is not allowed.")


@pytest.mark.asyncio
async def test_execute_allows_get_command() -> None:
    mgr = RedisManager()
    mgr._available = True
    mock_conn = AsyncMock()
    mock_conn.execute_command = AsyncMock(return_value="bar")
    mgr._connections["default"] = mock_conn
    result = await mgr.execute("GET", ["foo"])
    assert result == "bar"
    mock_conn.execute_command.assert_awaited_once_with("GET", "foo")


@pytest.mark.asyncio
async def test_execute_returns_nil_for_none() -> None:
    mgr = RedisManager()
    mgr._available = True
    mock_conn = AsyncMock()
    mock_conn.execute_command = AsyncMock(return_value=None)
    mgr._connections["default"] = mock_conn
    result = await mgr.execute("GET", ["missing"])
    assert result == "(nil)"


@pytest.mark.asyncio
async def test_execute_formats_list_result() -> None:
    mgr = RedisManager()
    mgr._available = True
    mock_conn = AsyncMock()
    mock_conn.execute_command = AsyncMock(return_value=["a", "b", "c"])
    mgr._connections["default"] = mock_conn
    result = await mgr.execute("LRANGE", ["key", "0", "-1"])
    assert "Result (3 items):" in result
    assert "[0] a" in result
    assert "[2] c" in result


@pytest.mark.asyncio
async def test_execute_formats_dict_result() -> None:
    mgr = RedisManager()
    mgr._available = True
    mock_conn = AsyncMock()
    mock_conn.execute_command = AsyncMock(return_value={"field1": "val1", "field2": "val2"})
    mgr._connections["default"] = mock_conn
    result = await mgr.execute("HGETALL", ["myhash"])
    assert "Result (2 keys):" in result
    assert "field1: val1" in result


@pytest.mark.asyncio
async def test_execute_handles_connection_error() -> None:
    mgr = RedisManager()
    mgr._available = True
    mock_conn = AsyncMock()
    mock_conn.execute_command = AsyncMock(side_effect=ConnectionError("refused"))
    mgr._connections["default"] = mock_conn
    result = await mgr.execute("GET", ["key"])
    assert result.startswith("Error:")
    assert "refused" in result


@pytest.mark.asyncio
async def test_start_sets_available_when_import_succeeds() -> None:
    import sys

    mgr = RedisManager()
    fake_redis = SimpleNamespace(asyncio=SimpleNamespace())
    with patch.dict(sys.modules, {"redis": fake_redis, "redis.asyncio": fake_redis.asyncio}):
        await mgr.start()
    assert mgr.is_available is True


@pytest.mark.asyncio
async def test_start_sets_unavailable_on_import_error() -> None:
    import builtins
    import sys

    mgr = RedisManager()
    real_import = builtins.__import__

    def _mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "redis.asyncio" or name == "redis":
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    # Remove redis from sys.modules so import is actually attempted
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.startswith("redis")}
    try:
        with patch("builtins.__import__", side_effect=_mock_import):
            await mgr.start()
    finally:
        sys.modules.update(saved)
    assert mgr.is_available is False


def test_get_redis_manager_singleton() -> None:
    import koda.services.redis_manager as mod

    mod._manager = None
    m1 = get_redis_manager()
    m2 = get_redis_manager()
    assert m1 is m2
    mod._manager = None  # cleanup


# ---------------------------------------------------------------------------
# tool_dispatcher handler tests
# ---------------------------------------------------------------------------


def _make_ctx() -> object:
    return SimpleNamespace(
        user_id=1,
        chat_id=1,
        work_dir="/tmp",
        user_data={},
        agent=None,
        agent_mode="normal",
        task_id=None,
        dry_run=False,
        scheduled_job_id=None,
        scheduled_run_id=None,
    )


@pytest.mark.asyncio
async def test_handler_disabled() -> None:
    with patch("koda.services.tool_dispatcher.REDIS_ENABLED", False):
        from koda.services.tool_dispatcher import _handle_redis_query

        result = await _handle_redis_query({"command": "GET", "args": ["k"]}, _make_ctx())
    assert result.success is False
    assert "not enabled" in result.output.lower()


@pytest.mark.asyncio
async def test_handler_missing_command() -> None:
    with patch("koda.services.tool_dispatcher.REDIS_ENABLED", True):
        from koda.services.tool_dispatcher import _handle_redis_query

        result = await _handle_redis_query({}, _make_ctx())
    assert result.success is False
    assert "command" in result.output.lower()


@pytest.mark.asyncio
async def test_handler_unavailable_package() -> None:
    mock_mgr = RedisManager()
    mock_mgr._available = False
    with (
        patch("koda.services.tool_dispatcher.REDIS_ENABLED", True),
        patch("koda.services.redis_manager.get_redis_manager", return_value=mock_mgr),
    ):
        # Re-import to pick up the patched module
        from koda.services.tool_dispatcher import _handle_redis_query

        result = await _handle_redis_query({"command": "GET", "args": ["k"]}, _make_ctx())
    assert result.success is False
    assert "not available" in result.output.lower()


# ---------------------------------------------------------------------------
# tool_prompt integration test
# ---------------------------------------------------------------------------


def test_prompt_omits_native_redis_section() -> None:
    from koda.services.tool_prompt import build_agent_tools_prompt

    prompt = build_agent_tools_prompt()
    assert "### Redis" not in prompt
    assert "redis_query" not in prompt
