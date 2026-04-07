"""Tests for mongo_manager and the mongo_query tool handler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.mongo_manager import MongoManager, get_mongo_manager

# ---------------------------------------------------------------------------
# MongoManager unit tests
# ---------------------------------------------------------------------------


class TestMongoManagerInitialState:
    def test_not_available_by_default(self):
        mgr = MongoManager()
        assert mgr.is_available is False
        assert mgr._clients == {}

    @pytest.mark.asyncio
    async def test_start_marks_unavailable_when_motor_missing(self):
        mgr = MongoManager()
        with patch.dict("sys.modules", {"motor": None, "motor.motor_asyncio": None}):
            await mgr.start()
        assert mgr.is_available is False

    @pytest.mark.asyncio
    async def test_stop_clears_clients(self):
        mgr = MongoManager()
        mock_client = MagicMock()
        mgr._clients["default"] = mock_client
        await mgr.stop()
        assert mgr._clients == {}
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_returns_error_on_failure(self):
        mgr = MongoManager()
        mgr._available = True
        with patch.object(mgr, "_get_client", side_effect=ValueError("MONGO_URL not configured.")):
            result = await mgr.query("testdb", "coll")
        assert result.startswith("Error")


class _FakeCursor:
    """Minimal async-iterable cursor stub for tests."""

    def __init__(self, docs):
        self._docs = list(docs)

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class TestMongoManagerQuery:
    @pytest.mark.asyncio
    async def test_query_formats_results(self):
        mgr = MongoManager()
        mgr._available = True

        cursor = _FakeCursor([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}])

        mock_coll = MagicMock()
        mock_coll.find.return_value = cursor
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch.object(mgr, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await mgr.query("testdb", "users")

        assert "testdb.users" in result
        assert "2 docs" in result
        assert "Alice" in result

    @pytest.mark.asyncio
    async def test_query_no_documents(self):
        mgr = MongoManager()
        mgr._available = True

        cursor = _FakeCursor([])

        mock_coll = MagicMock()
        mock_coll.find.return_value = cursor
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_coll)
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        with patch.object(mgr, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await mgr.query("testdb", "users")

        assert "No documents found" in result


# ---------------------------------------------------------------------------
# Tool dispatcher handler tests
# ---------------------------------------------------------------------------


def _make_ctx(**overrides):
    from koda.services.tool_dispatcher import ToolContext

    defaults = dict(
        user_id=111,
        chat_id=111,
        work_dir="/tmp",
        user_data={},
        agent=AsyncMock(),
        agent_mode="autonomous",
    )
    defaults.update(overrides)
    return ToolContext(**defaults)


class TestMongoQueryHandler:
    @pytest.mark.asyncio
    async def test_disabled_returns_error(self):
        from koda.services.tool_dispatcher import _handle_mongo_query

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.MONGO_ENABLED", False):
            result = await _handle_mongo_query({}, ctx)
        assert result.success is False
        assert "not enabled" in result.output

    @pytest.mark.asyncio
    async def test_missing_params_returns_error(self):
        from koda.services.tool_dispatcher import _handle_mongo_query

        ctx = _make_ctx()
        with patch("koda.services.tool_dispatcher.MONGO_ENABLED", True):
            result = await _handle_mongo_query({"database": "db"}, ctx)
        assert result.success is False
        assert "Missing" in result.output

    @pytest.mark.asyncio
    async def test_motor_not_available(self):
        from koda.services.tool_dispatcher import _handle_mongo_query

        ctx = _make_ctx()
        mock_mgr = MagicMock()
        mock_mgr.is_available = False
        with (
            patch("koda.services.tool_dispatcher.MONGO_ENABLED", True),
            patch("koda.services.mongo_manager._manager", mock_mgr),
            patch("koda.services.mongo_manager.get_mongo_manager", return_value=mock_mgr),
        ):
            result = await _handle_mongo_query({"database": "db", "collection": "coll"}, ctx)
        assert result.success is False
        assert "not available" in result.output

    @pytest.mark.asyncio
    async def test_successful_query(self):
        from koda.services.tool_dispatcher import _handle_mongo_query

        ctx = _make_ctx()
        mock_mgr = MagicMock()
        mock_mgr.is_available = True
        mock_mgr.query = AsyncMock(return_value="Results from db.coll (1 docs):\n{}")
        with (
            patch("koda.services.tool_dispatcher.MONGO_ENABLED", True),
            patch("koda.services.mongo_manager._manager", mock_mgr),
            patch("koda.services.mongo_manager.get_mongo_manager", return_value=mock_mgr),
        ):
            result = await _handle_mongo_query({"database": "db", "collection": "coll"}, ctx)
        assert result.success is True
        assert "Results" in result.output


# ---------------------------------------------------------------------------
# Prompt tests
# ---------------------------------------------------------------------------


class TestMongoPromptSection:
    def test_mongo_tools_are_not_advertised_in_runtime_prompt(self):
        from koda.services.tool_prompt import build_agent_tools_prompt

        prompt = build_agent_tools_prompt()
        assert "### MongoDB" not in prompt
        assert "`mongo_query`" not in prompt


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestGetMongoManager:
    def test_returns_singleton(self):
        import koda.services.mongo_manager as mod

        mod._manager = None
        m1 = get_mongo_manager()
        m2 = get_mongo_manager()
        assert m1 is m2
        mod._manager = None  # cleanup
