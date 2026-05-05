from __future__ import annotations

import inspect
import json
from typing import Any


def test_runtime_queue_postgres_store_serializes_text_columns(monkeypatch):
    from koda.services.runtime.postgres_store import PostgresRuntimeStore

    store = PostgresRuntimeStore.__new__(PostgresRuntimeStore)
    store._agent_scope = "koda"  # type: ignore[attr-defined]
    captured: dict[str, tuple[Any, ...]] = {}

    def fake_execute(_query: str, params: tuple[Any, ...]) -> int:
        captured["params"] = params
        return 1

    monkeypatch.setattr(store, "_execute", fake_execute)

    store.upsert_runtime_queue_item(
        task_id=1,
        user_id=2,
        chat_id=3,
        query_text="hello",
        payload_json={"image_paths": []},  # type: ignore[arg-type]
        recovery_count=0,
        last_recovered_at=["bad"],  # type: ignore[arg-type]
        source_kind=["telegram"],  # type: ignore[arg-type]
        last_error=[],  # type: ignore[arg-type]
    )

    params = captured["params"]
    assert isinstance(params[7], str)
    assert json.loads(params[7]) == {"image_paths": []}
    assert isinstance(params[9], str)
    assert isinstance(params[10], str)
    assert isinstance(params[11], str)


def test_runtime_event_postgres_store_serializes_artifact_refs(monkeypatch):
    from koda.services.runtime.postgres_store import PostgresRuntimeStore

    store = PostgresRuntimeStore.__new__(PostgresRuntimeStore)
    store._agent_scope = "koda"  # type: ignore[attr-defined]
    captured: dict[str, tuple[Any, ...]] = {}

    def fake_fetch_val(_query: str, params: tuple[Any, ...]) -> int:
        captured["params"] = params
        return 7

    monkeypatch.setattr(store, "_fetch_val", fake_fetch_val)

    event = store.add_event(
        task_id=1,
        env_id=None,
        attempt=1,
        phase="executing",
        event_type="artifact.created",
        severity="info",
        payload={"ok": True},
        artifact_refs=["file:a.txt"],
    )

    params = captured["params"]
    assert isinstance(params[8], str)
    assert json.loads(params[8]) == ["file:a.txt"]
    assert event["artifact_refs"] == ["file:a.txt"]


def test_runtime_queue_list_reconciles_uppercase_task_agent_scope() -> None:
    from koda.services.runtime.postgres_store import PostgresRuntimeStore

    source = inspect.getsource(PostgresRuntimeStore.list_runtime_queues)

    assert "lower(t.agent_id) = rq.agent_id" in source


def test_execution_episode_primary_path_serializes_json_fields(monkeypatch):
    from koda.state import knowledge_governance_store as store

    captured: dict[str, tuple[Any, ...]] = {}

    def fake_primary_fetch_val(_query: str, params: tuple[Any, ...], *, agent_id: str | None = None) -> int:
        del agent_id
        captured["params"] = params
        return 42

    monkeypatch.setattr(store, "_primary_enabled", lambda agent_id=None: True)
    monkeypatch.setattr(store, "primary_fetch_val", fake_primary_fetch_val)
    monkeypatch.setattr(store, "run_coro_sync", lambda value: value)

    episode_id = store.create_execution_episode(
        agent_id="koda",
        task_id=1,
        user_id=2,
        task_kind="chat",
        project_key="",
        environment="",
        team="",
        autonomy_tier="",
        approval_mode="",
        status="completed",
        confidence_score=1.0,
        verified_before_finalize=True,
        stale_sources_present=False,
        ungrounded_operationally=False,
        plan={"steps": []},
        source_refs=[{"id": "source"}],
        tool_trace=[{"tool": "voice"}],
        winning_sources=["source"],
        answer_gate_reasons=["ok"],
    )

    params = captured["params"]
    assert episode_id == 42
    for index in (14, 15, 16, 21, 24):
        assert isinstance(params[index], str)
        json.loads(params[index])
