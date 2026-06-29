"""Focused tests for graph reads now going through gRPC only."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_list_knowledge_graph_async_uses_retrieval_engine(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    events: list[object] = []

    class FakeClient:
        async def start(self) -> None:
            events.append("start")

        async def stop(self) -> None:
            events.append("stop")

        def list_graph(self, *, entity_type: str | None = None, limit: int = 200) -> dict[str, object]:
            events.append(("list_graph", entity_type, limit))
            return {"entities": [{"entity_key": "p1"}], "relations": []}

    monkeypatch.setattr(manager_mod, "build_retrieval_engine_client", lambda agent_id: FakeClient())

    result = await manager.list_knowledge_graph_async("AGENT_A", entity_type="project", limit=25)

    assert result == {"entities": [{"entity_key": "p1"}], "relations": []}
    assert events == ["start", ("list_graph", "project", 25), "stop"]


@pytest.mark.asyncio
async def test_list_knowledge_graph_async_fails_closed_without_local_fallback(monkeypatch):
    import koda.control_plane.manager as manager_mod

    manager = object.__new__(manager_mod.ControlPlaneManager)
    manager._knowledge_repository = lambda agent_id: SimpleNamespace(  # type: ignore[attr-defined]
        list_knowledge_graph=lambda **kwargs: pytest.fail("should not use local graph repository")
    )

    class BrokenClient:
        async def start(self) -> None:
            raise RuntimeError("boom")

        async def stop(self) -> None:
            return None

    monkeypatch.setattr(manager_mod, "build_retrieval_engine_client", lambda agent_id: BrokenClient())

    with pytest.raises(RuntimeError, match="grpc_retrieval_engine_graph_list_failed"):
        await manager.list_knowledge_graph_async("AGENT_A", entity_type="project", limit=10)
