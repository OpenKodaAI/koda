"""Tests for the Postgres runtime store."""

from __future__ import annotations

from typing import Any

from koda.services.runtime.postgres_store import PostgresRuntimeStore


def test_postgres_runtime_store_exposes_source_root_alias_in_environment_queries():
    class _CapturingStore(PostgresRuntimeStore):
        def __init__(self) -> None:
            self._agent_scope = "test-agent"
            self.queries: list[str] = []

        def _fetch_one(self, query: str, params: Any = ()) -> dict[str, Any] | None:  # type: ignore[override]
            self.queries.append(query)
            return {"id": 1, "base_work_dir": "/repo", "source_root_path": "/repo"}

        def _fetch_all(self, query: str, params: Any = ()) -> list[dict[str, Any]]:  # type: ignore[override]
            self.queries.append(query)
            return [{"id": 1, "base_work_dir": "/repo", "source_root_path": "/repo"}]

    store = _CapturingStore()

    assert store.get_environment(1) == {
        "id": 1,
        "base_work_dir": "/repo",
        "source_root_path": "/repo",
        "source_root_exists": False,
    }
    assert store.get_environment_by_task(41) is not None
    assert store.list_environments()[0]["source_root_path"] == "/repo"
    assert store.list_environments()[0]["source_root_exists"] is False
    assert all("base_work_dir AS source_root_path" in query for query in store.queries)
