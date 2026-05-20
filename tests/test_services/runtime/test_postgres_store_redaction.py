from __future__ import annotations

import pytest

from koda.services.runtime.postgres_store import PostgresRuntimeStore


def test_add_artifact_rejects_invalid_runtime_path():
    store = PostgresRuntimeStore()
    store._fetch_val = lambda query, params=(): 1  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="runtime path contains invalid characters"):
        store.add_artifact(
            task_id=1,
            env_id=2,
            artifact_kind="log",
            label="stdout",
            path="/tmp/runtime\nstdout.log",
            metadata={"status": "ok"},
        )


def test_update_task_runtime_redacts_error_message_before_execute():
    store = PostgresRuntimeStore()
    captured: dict[str, object] = {}

    def _capture(query: str, params=()) -> int:
        captured["query"] = query
        captured["params"] = tuple(params)
        return 1

    store._execute = _capture  # type: ignore[method-assign]

    store.update_task_runtime(
        42,
        status="failed",
        error_message="Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
    )

    params = captured["params"]
    assert isinstance(params, tuple)
    assert "Bearer [REDACTED]" in params[2]


def test_upsert_process_redacts_command_before_persisting():
    store = PostgresRuntimeStore()
    captured: dict[str, object] = {}
    store._fetch_one = lambda query, params=(): None  # type: ignore[method-assign]

    def _capture(query: str, params=()):
        captured["query"] = query
        captured["params"] = tuple(params)
        return 9

    store._fetch_val = _capture  # type: ignore[method-assign]

    process_id = store.upsert_process(
        task_id=1,
        env_id=2,
        pid=100,
        pgid=100,
        role="worker",
        command="curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456' https://example.com",
    )

    params = captured["params"]
    assert process_id == 9
    assert isinstance(params, tuple)
    assert "Bearer [REDACTED]" in params[8]
