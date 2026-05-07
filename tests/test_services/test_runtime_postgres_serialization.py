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


def test_runtime_artifact_reads_parse_text_metadata(monkeypatch):
    from koda.services.runtime.postgres_store import PostgresRuntimeStore

    store = PostgresRuntimeStore.__new__(PostgresRuntimeStore)
    store._agent_scope = "koda"  # type: ignore[attr-defined]

    monkeypatch.setattr(
        store,
        "_fetch_all",
        lambda _query, _params: [
            {
                "id": 7,
                "task_id": 1,
                "env_id": None,
                "artifact_kind": "image",
                "label": "render.png",
                "path": "/tmp/render.png",
                "metadata_json": '{"artifact_engine_ready": true, "object_key": "koda/render.png"}',
                "created_at": "2026-05-05T00:00:00Z",
                "expires_at": None,
            }
        ],
    )

    artifacts = store.list_artifacts(1)

    assert artifacts[0]["metadata"]["artifact_engine_ready"] is True
    assert artifacts[0]["metadata"]["object_key"] == "koda/render.png"


def test_runtime_artifact_reads_are_case_insensitive_for_agent_scope(monkeypatch):
    from koda.services.runtime.postgres_store import PostgresRuntimeStore

    store = PostgresRuntimeStore.__new__(PostgresRuntimeStore)
    store._agent_scope = "KODA"  # type: ignore[attr-defined]
    captured: dict[str, tuple[str, tuple[Any, ...]]] = {}

    def fake_fetch_all(query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        captured["all"] = (query, params)
        return []

    def fake_fetch_one(query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        captured["one"] = (query, params)
        return None

    monkeypatch.setattr(store, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(store, "_fetch_one", fake_fetch_one)

    assert store.list_artifacts(453) == []
    assert store.get_artifact(428) is None

    list_query, list_params = captured["all"]
    get_query, get_params = captured["one"]
    assert "lower(agent_id) = lower(?)" in list_query
    assert "lower(agent_id) = lower(?)" in get_query
    assert list_params == ("KODA", 453)
    assert get_params == ("KODA", 428)


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
