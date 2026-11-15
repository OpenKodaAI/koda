"""Agent scope of the ``tasks`` rows: one helper for the writer and the runtime store (D-293)."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.parametrize(
    ("agent_id", "expected"),
    [
        ("Agent_A", "AGENT_A"),
        ("agent_a", "AGENT_A"),
        ("  aGeNt_B  ", "AGENT_B"),
        ("AGENT_A", "AGENT_A"),
    ],
)
def test_task_agent_scope_upper_cases_mixed_case_ids(agent_id: str, expected: str) -> None:
    from koda.state.agent_scope import task_agent_scope

    assert task_agent_scope(agent_id) == expected


def test_task_agent_scope_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from koda.state import agent_scope

    monkeypatch.setattr(agent_scope, "AGENT_ID", None)

    assert agent_scope.task_agent_scope(None) == "DEFAULT"
    assert agent_scope.task_agent_scope("   ") == "DEFAULT"


def test_runtime_store_reads_tasks_with_the_scope_history_store_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mixed-case ``AGENT_ID``: the runtime store's ``tasks`` queries use the writer's scope."""
    from koda.services.runtime import postgres_store
    from koda.state import history_store

    monkeypatch.setattr(history_store, "AGENT_ID", "Agent_Mixed")
    monkeypatch.setattr(postgres_store, "AGENT_ID", "Agent_Mixed")
    store = postgres_store.PostgresRuntimeStore()
    params: list[tuple[Any, ...]] = []

    def _capture(_query: str, values: Any = ()) -> Any:
        params.append(tuple(values))
        return []

    monkeypatch.setattr(store, "_execute", _capture)
    monkeypatch.setattr(store, "_fetch_one", _capture)
    monkeypatch.setattr(store, "_fetch_all", _capture)

    store.get_task_runtime(7)
    store.update_task_runtime(7, status="cancelled")
    store.heartbeat(7, None, phase="executing")
    store.list_task_ids_for_session("sess-1")

    writer_scope = history_store._current_agent_scope()
    assert writer_scope == "AGENT_MIXED"
    assert [values[-2:] for values in params[:3]] == [(writer_scope, 7)] * 3
    assert params[3] == (writer_scope, "sess-1")
    # The runtime-owned ``runtime_*`` tables keep their lower-case scope.
    assert store._agent_scope == "agent_mixed"
