from __future__ import annotations

import pytest

from koda.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_memory_store_search_sources_with_memory_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    store = MemoryStore("AGENT_A")

    class _FakeEngine:
        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        async def recall(
            self,
            *,
            query: str,
            limit: int,
            user_id: int | None = None,
            memory_types: list[str] | None = None,
            project_key: str = "",
            environment: str = "",
            team: str = "",
            origin_kinds: list[str] | None = None,
            session_id: str | None = None,
            source_query_id: int | None = None,
            source_task_id: int | None = None,
            source_episode_id: int | None = None,
            memory_statuses: list[str] | None = None,
            allowed_layers: list[str] | None = None,
            allowed_retrieval_sources: list[str] | None = None,
        ) -> list[dict[str, object]]:
            assert query == "deploy api"
            assert user_id == 1
            assert limit >= 2
            assert memory_types == []
            assert allowed_layers == []
            assert allowed_retrieval_sources == []
            return [
                {
                    "memory_id": 2,
                    "score": 0.95,
                    "retrieval_source": "lexical",
                    "layer": "conversational",
                    "memory": {
                        "id": 2,
                        "user_id": 1,
                        "memory_type": "fact",
                        "content": "second memory",
                        "agent_id": "agent_a",
                        "memory_status": "active",
                    },
                },
                {
                    "memory_id": 1,
                    "score": 0.20,
                    "retrieval_source": "lexical",
                    "layer": "conversational",
                    "memory": {
                        "id": 1,
                        "user_id": 1,
                        "memory_type": "fact",
                        "content": "first memory",
                        "agent_id": "agent_a",
                        "memory_status": "active",
                    },
                },
            ]

        def health(self) -> dict[str, object]:
            return {
                "ready": True,
                "cutover_allowed": True,
                "details": {"capabilities": "recall"},
            }

    monkeypatch.setattr(store, "_memory_engine", _FakeEngine())
    monkeypatch.setattr(store, "_memory_engine_started", False)

    results = await store.search("deploy api", user_id=1, n_results=2)

    assert [item.memory.id for item in results] == [2, 1]
    assert results[0].selection_reasons[-1] == "rust_grpc_recall"
