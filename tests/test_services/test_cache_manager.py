"""Tests for response cache manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koda.services.cache_manager import (
    CacheManager,
    build_cache_scope_fingerprint,
    looks_like_provider_error_response,
    normalize_query,
    query_hash,
    scoped_query_hash,
    should_cache,
)


class TestNormalizeQuery:
    def test_strip_and_lowercase(self):
        assert normalize_query("  HELLO WORLD  ") == "hello world"

    def test_collapse_whitespace(self):
        assert normalize_query("hello   world\n\tfoo") == "hello world foo"

    def test_remove_conversational_prefix(self):
        assert normalize_query("por favor me ajude com isso") == "me ajude com isso"
        assert normalize_query("Can you help me with this?") == "help me with this?"


class TestQueryHash:
    def test_deterministic(self):
        assert query_hash("hello world") == query_hash("hello world")

    def test_scope_changes_hash(self):
        scope_a = build_cache_scope_fingerprint(agent_id="AGENT_A", work_dir="/tmp/a")
        scope_b = build_cache_scope_fingerprint(agent_id="AGENT_A", work_dir="/tmp/b")
        assert scoped_query_hash("hello", scope_fingerprint=scope_a) != scoped_query_hash(
            "hello",
            scope_fingerprint=scope_b,
        )


class TestShouldCache:
    def test_rejects_short_or_error_responses(self):
        assert not should_cache("question", "ok")
        assert not should_cache("question", "Error: something failed badly")

    def test_rejects_temporal_or_volatile_queries(self):
        assert not should_cache("o que está acontecendo agora", "a" * 100)
        assert not should_cache("git status", "a" * 100)

    def test_accepts_stable_answer(self):
        assert should_cache("explain python decorators", "a" * 100)


class TestPoisonedResponseDetection:
    def test_detects_provider_error_text(self):
        assert looks_like_provider_error_response("Claude authentication failed. Reauthenticate the Claude CLI.")

    def test_ignores_normal_answer(self):
        assert not looks_like_provider_error_response("Aqui está a análise do card SIM-410 com próximos passos.")


class TestCacheManager:
    @pytest.mark.asyncio
    async def test_not_initialized_returns_none(self):
        cm = CacheManager(agent_id="test")
        assert await cm.lookup("test", 111) is None

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_requires_primary_backend(self):
        with patch("koda.services.cache_manager.STATE_BACKEND", "disabled"):
            cm = CacheManager(agent_id="test")
            await cm.initialize()

        assert cm._initialized is False

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_enables_primary_mode(self):
        with patch("koda.services.cache_manager.STATE_BACKEND", "postgres"):
            cm = CacheManager(agent_id="test")
            await cm.initialize()

        assert cm._initialized is True

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @pytest.mark.asyncio
    async def test_initialize_reuses_memory_store_model(self):
        cm = CacheManager(agent_id="test")
        fake_model = object()
        memory_store = MagicMock()
        memory_store._get_model_safe = AsyncMock(return_value=fake_model)

        with patch("koda.services.cache_manager.STATE_BACKEND", "postgres"):
            await cm.initialize(memory_store=memory_store)

        assert cm._model is fake_model
        memory_store._get_model_safe.assert_awaited_once()

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @patch("koda.services.cache_manager.cache_lookup_by_hash")
    @pytest.mark.asyncio
    async def test_exact_lookup(self, mock_lookup):
        mock_lookup.return_value = (1, "cached response", 0.05)
        cm = CacheManager(agent_id="test")
        cm._initialized = True

        with patch("koda.services.cache_manager.cache_record_hit"):
            result = await cm.lookup("hello world", 111, work_dir="/tmp/workspace-a")

        assert result is not None
        assert result.match_type == "exact"
        assert result.response == "cached response"
        assert result.similarity == 1.0

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @patch("koda.services.cache_manager.cache_invalidate_entry")
    @patch("koda.services.cache_manager.cache_lookup_by_hash")
    @pytest.mark.asyncio
    async def test_exact_lookup_invalidates_poisoned_response(self, mock_lookup, mock_invalidate):
        mock_lookup.return_value = (
            1,
            'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error"}}',
            0.0,
        )
        cm = CacheManager(agent_id="test")
        cm._initialized = True

        result = await cm.lookup("hello world", 111, work_dir="/tmp/workspace-a")

        assert result is None
        mock_invalidate.assert_called_once_with(1, agent_id="test")

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @patch("koda.services.cache_manager.cache_lookup_by_hash")
    @patch("koda.services.cache_manager.cache_list_active_entries")
    @patch("koda.services.cache_manager.cache_get_by_id")
    @pytest.mark.asyncio
    async def test_primary_lookup_uses_canonical_rows(self, mock_get_by_id, mock_list_entries, mock_hash_lookup):
        class FakeModel:
            def encode(self, text, normalize_embeddings=True):  # noqa: ANN001
                def _one(value: str) -> list[float]:
                    payload = str(value or "").lower()
                    return [
                        1.0 if "deploy" in payload else 0.0,
                        1.0 if "payments" in payload else 0.0,
                        float(len(payload.split())),
                    ]

                if isinstance(text, list):
                    return MagicMock(tolist=lambda: [_one(item) for item in text])
                return MagicMock(tolist=lambda: _one(text))

        mock_hash_lookup.return_value = None
        mock_get_by_id.return_value = ("Use the rollback helper.", 0.03)
        mock_list_entries.return_value = [
            {
                "id": 42,
                "query_text": "deploy payments rollback",
                "response_text": "Use the rollback helper.",
                "cost_usd": 0.03,
                "work_dir": "/tmp/workspace-a",
            }
        ]

        with (
            patch("koda.services.cache_manager.STATE_BACKEND", "postgres"),
            patch("koda.services.cache_manager.cache_record_hit") as mock_record_hit,
        ):
            cm = CacheManager(agent_id="test")
            cm._initialized = True
            cm._model = FakeModel()
            result = await cm.lookup("deploy payments", 111, work_dir="/tmp/workspace-a")

        assert result is not None
        assert result.cache_id == 42
        assert result.match_type == "fuzzy_auto"
        mock_record_hit.assert_called_once_with(42, agent_id="test")

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @patch("koda.services.cache_manager.cache_lookup_by_hash")
    @patch("koda.services.cache_manager.cache_list_active_entries")
    @patch("koda.services.cache_manager.cache_get_by_id")
    @pytest.mark.asyncio
    async def test_primary_lookup_fails_closed_for_extended_scope(
        self,
        mock_get_by_id,
        mock_list_entries,
        mock_hash_lookup,
    ):
        mock_hash_lookup.return_value = None
        mock_get_by_id.return_value = ("Use the rollback helper.", 0.03)
        mock_list_entries.return_value = [
            {
                "id": 42,
                "query_text": "deploy payments rollback",
                "response_text": "Use the rollback helper.",
                "cost_usd": 0.03,
                "work_dir": "/tmp/workspace-a",
            }
        ]

        with patch("koda.services.cache_manager.STATE_BACKEND", "postgres"):
            cm = CacheManager(agent_id="test")
            cm._initialized = True
            cm._model = MagicMock()
            result = await cm.lookup(
                "deploy payments",
                111,
                work_dir="/tmp/workspace-a",
                source_scope=("policy:deploy",),
            )

        assert result is None

    @patch("koda.services.cache_manager.CACHE_ENABLED", True)
    @patch("koda.services.cache_manager.cache_upsert")
    @pytest.mark.asyncio
    async def test_store_success(self, mock_upsert):
        mock_upsert.return_value = 42
        cm = CacheManager(agent_id="test")
        cm._initialized = True

        result = await cm.store(111, "test query", "test response", "claude-sonnet-4-6", 0.01, "/tmp")
        assert result == 42
        mock_upsert.assert_called_once()

    @patch("koda.services.cache_manager.cache_invalidate_user")
    @pytest.mark.asyncio
    async def test_invalidate_user(self, mock_inv):
        mock_inv.return_value = 5
        cm = CacheManager(agent_id="test")
        result = await cm.invalidate_user(111)
        assert result == 5
        mock_inv.assert_called_once_with(111, agent_id="test")

    @patch("koda.services.cache_manager.cache_get_stats")
    @pytest.mark.asyncio
    async def test_get_stats(self, mock_stats):
        mock_stats.return_value = {"entries": 10, "total_hits": 50, "estimated_savings_usd": 1.23}
        cm = CacheManager(agent_id="test")
        result = await cm.get_stats(111)
        assert result["entries"] == 10
        assert result["total_hits"] == 50
        mock_stats.assert_called_once_with(111, agent_id="test")


def test_get_cache_manager_is_scoped_per_agent():
    from koda.services import cache_manager as module

    module._MANAGERS.clear()

    first = module.get_cache_manager("AGENT-A")
    second = module.get_cache_manager("agent-a")
    third = module.get_cache_manager("agent-b")

    assert first is second
    assert first is not third
    assert first._agent_id == "agent-a"
    assert third._agent_id == "agent-b"
