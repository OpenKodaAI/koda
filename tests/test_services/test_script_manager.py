"""Tests for script library manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.script_manager import ScriptManager, _extract_title


class TestExtractTitle:
    def test_function_name(self):
        code = "def calculate_sum(a, b):\n    return a + b"
        assert _extract_title(code, "python") == "calculate_sum"

    def test_class_name(self):
        code = "class MyHandler:\n    pass"
        assert _extract_title(code, "python") == "MyHandler"

    def test_js_function(self):
        code = "function fetchData() {\n  return fetch('/api');\n}"
        assert _extract_title(code, "javascript") == "fetchData"

    def test_comment_fallback(self):
        code = "# Database migration script\nresult = migrate_schema()"
        assert _extract_title(code, "python") == "Database migration script"


class TestScriptManager:
    @pytest.mark.asyncio
    async def test_not_initialized_returns_empty(self):
        sm = ScriptManager(agent_id="test")
        assert await sm.search("test", 111) == []

    @pytest.mark.asyncio
    async def test_save_returns_none_when_disabled(self):
        sm = ScriptManager(agent_id="test")
        assert await sm.save(111, "title", "desc", "content") is None

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_reuses_memory_store_model(self):
        sm = ScriptManager(agent_id="test")
        fake_model = object()
        memory_store = MagicMock()
        memory_store._get_model_safe = AsyncMock(return_value=fake_model)

        with patch("koda.services.script_manager.STATE_BACKEND", "postgres"):
            await sm.initialize(memory_store=memory_store)

        assert sm._model is fake_model
        memory_store._get_model_safe.assert_awaited_once()

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_requires_primary_backend(self):
        with patch("koda.services.script_manager.STATE_BACKEND", "disabled"):
            sm = ScriptManager(agent_id="test")
            await sm.initialize()

        assert sm._initialized is False

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_enables_primary_mode(self):
        with patch("koda.services.script_manager.STATE_BACKEND", "postgres"):
            sm = ScriptManager(agent_id="test")
            await sm.initialize()

        assert sm._initialized is True


class TestScriptManagerSaveAndSearch:
    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @patch("koda.services.script_manager.upsert_asset")
    @patch("koda.services.script_manager.script_insert")
    @patch("koda.services.script_manager.script_list_by_user")
    @pytest.mark.asyncio
    async def test_save_success(self, mock_list, mock_insert, _mock_upsert_asset):
        mock_list.return_value = []
        mock_insert.return_value = 42

        sm = ScriptManager(agent_id="test")
        sm._initialized = True

        result = await sm.save(111, "test_func", "A test function", "def test(): pass", "python", ["test"])
        assert result == 42
        mock_insert.assert_called_once_with(
            111,
            "test_func",
            "A test function",
            "python",
            "def test(): pass",
            None,
            '["test"]',
            "test",
        )

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @patch("koda.services.script_manager.script_insert")
    @patch("koda.services.script_manager.script_list_by_user")
    @patch("koda.services.script_manager.SCRIPT_MAX_PER_USER", 5)
    @pytest.mark.asyncio
    async def test_save_at_limit(self, mock_list, mock_insert):
        mock_list.return_value = [(i,) for i in range(5)]
        mock_insert.return_value = None

        sm = ScriptManager(agent_id="test")
        sm._initialized = True

        assert await sm.save(111, "title", "desc", "content") is None

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @patch("koda.services.script_manager.script_list_for_semantic_index")
    @pytest.mark.asyncio
    async def test_primary_search_uses_canonical_store(self, mock_index_rows):
        class FakeModel:
            def encode(self, text, normalize_embeddings=True):  # noqa: ANN001
                def _one(value: str) -> list[float]:
                    payload = str(value or "").lower()
                    return [
                        1.0 if "helper" in payload else 0.0,
                        1.0 if "python" in payload else 0.0,
                        float(len(payload.split())),
                    ]

                if isinstance(text, list):
                    return MagicMock(tolist=lambda: [_one(item) for item in text])
                return MagicMock(tolist=lambda: _one(text))

        with patch("koda.services.script_manager.STATE_BACKEND", "postgres"):
            sm = ScriptManager(agent_id="test")
            sm._initialized = True
            sm._model = FakeModel()
            mock_index_rows.return_value = [
                {
                    "id": 42,
                    "title": "helper_func",
                    "description": "A helper function",
                    "language": "python",
                    "content": "def helper(): pass",
                    "use_count": 3,
                    "quality_score": 0.7,
                    "is_active": True,
                }
            ]

            results = await sm.search("helper python", 111)

        assert len(results) == 1
        assert results[0].script_id == 42
        assert results[0].quality_score == pytest.approx(0.7)
        assert results[0].use_count == 3


class TestAutoExtract:
    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @patch("koda.services.script_manager.SCRIPT_AUTO_EXTRACT", True)
    @patch("koda.services.script_manager.upsert_asset")
    @patch("koda.services.script_manager.script_insert")
    @patch("koda.services.script_manager.script_list_by_user")
    @pytest.mark.asyncio
    async def test_auto_extract_code_blocks(self, mock_list, mock_insert, _mock_upsert_asset):
        mock_list.return_value = []
        mock_insert.return_value = 99

        sm = ScriptManager(agent_id="test")
        sm._initialized = True

        response = (
            "Here's the solution:\n\n"
            "```python\n"
            "def calculate_fibonacci(n):\n"
            "    if n <= 1:\n"
            "        return n\n"
            "    a, b = 0, 1\n"
            "    for _ in range(2, n + 1):\n"
            "        a, b = b, a + b\n"
            "    return b\n"
            "```\n"
        )

        ids = await sm.auto_extract("fibonacci function", response, 111)
        assert ids == [99]

    @patch("koda.services.script_manager.SCRIPT_LIBRARY_ENABLED", True)
    @patch("koda.services.script_manager.SCRIPT_AUTO_EXTRACT", True)
    @pytest.mark.asyncio
    async def test_auto_extract_skips_short_blocks(self):
        sm = ScriptManager(agent_id="test")
        sm._initialized = True

        ids = await sm.auto_extract("test", "```python\nx = 1\n```", 111)
        assert ids == []


class TestScriptManagerQuality:
    @patch("koda.services.script_manager.script_update_quality")
    @pytest.mark.asyncio
    async def test_update_quality(self, mock_update):
        sm = ScriptManager(agent_id="test")
        await sm.update_quality(42, 0.1)
        mock_update.assert_called_once_with(42, 0.1, agent_id="test")

    @patch("koda.services.script_manager.script_record_use")
    @pytest.mark.asyncio
    async def test_record_use(self, mock_record):
        sm = ScriptManager(agent_id="test")
        await sm.record_use(42)
        mock_record.assert_called_once_with(42, agent_id="test")

    @patch("koda.services.script_manager.script_record_use")
    @pytest.mark.asyncio
    async def test_record_use_normalizes_agent_scope(self, mock_record):
        sm = ScriptManager(agent_id="AGENT-Alpha")
        await sm.record_use(42)
        mock_record.assert_called_once_with(42, agent_id="agent-alpha")

    @patch("koda.services.script_manager.upsert_asset")
    @patch("koda.services.script_manager.script_get")
    @patch("koda.services.script_manager.script_record_use")
    @pytest.mark.asyncio
    async def test_record_use_refreshes_asset_registry(self, mock_record, mock_script_get, mock_upsert_asset):
        sm = ScriptManager(agent_id="test")
        sm._model = MagicMock()
        sm._model.encode.return_value = MagicMock(tolist=lambda: [1.0, 0.0, 1.0])
        mock_script_get.return_value = (
            8,
            111,
            "helper_func",
            "Canonical helper",
            "python",
            "def helper(): pass",
            "find helper",
            "[]",
            5,
            None,
            0.9,
            "",
            "",
            1,
        )

        await sm.record_use(8)

        mock_record.assert_called_once_with(8, agent_id="test")
        assert mock_upsert_asset.called


class TestScriptManagerDeactivate:
    @patch("koda.services.script_manager.disable_asset")
    @patch("koda.services.script_manager.script_deactivate")
    @pytest.mark.asyncio
    async def test_deactivate_success(self, mock_deactivate, mock_disable_asset):
        mock_deactivate.return_value = True
        sm = ScriptManager(agent_id="test")
        result = await sm.deactivate(42, 111)
        assert result is True
        mock_deactivate.assert_called_once_with(42, 111, agent_id="test")
        mock_disable_asset.assert_called_once_with("script:42", agent_id="test")

    @patch("koda.services.script_manager.disable_asset")
    @patch("koda.services.script_manager.script_deactivate")
    @pytest.mark.asyncio
    async def test_deactivate_not_found(self, mock_deactivate, mock_disable_asset):
        mock_deactivate.return_value = False
        sm = ScriptManager(agent_id="test")
        result = await sm.deactivate(999, 111)
        assert result is False
        mock_deactivate.assert_called_once_with(999, 111, agent_id="test")
        mock_disable_asset.assert_not_called()


class TestStats:
    @patch("koda.services.script_manager.script_get_stats")
    @pytest.mark.asyncio
    async def test_get_stats(self, mock_stats):
        mock_stats.return_value = {"scripts": 10, "total_uses": 50}
        sm = ScriptManager(agent_id="test")
        result = await sm.get_stats(111)
        assert result["scripts"] == 10
        assert result["total_uses"] == 50
        mock_stats.assert_called_once_with(111, agent_id="test")


def test_get_script_manager_is_scoped_per_agent():
    from koda.services import script_manager as module

    module._MANAGERS.clear()

    first = module.get_script_manager("AGENT-A")
    second = module.get_script_manager("agent-a")
    third = module.get_script_manager("agent-b")

    assert first is second
    assert first is not third
    assert first._agent_id == "agent-a"
    assert third._agent_id == "agent-b"
