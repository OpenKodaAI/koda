"""Tests for the runtime store public wrapper."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from koda.services.runtime.store import RuntimeStore


class _RoundTripDelegate:
    def __init__(self) -> None:
        self._next_id = 100
        self._tasks: dict[int, dict[str, Any]] = {}
        self._environments: dict[int, dict[str, Any]] = {}
        self._events: dict[int, list[dict[str, Any]]] = {}
        self._artifacts: dict[int, list[dict[str, Any]]] = {}
        self._browser_sessions: dict[int, list[dict[str, Any]]] = {}
        self._loop_cycles: dict[int, list[dict[str, Any]]] = {}
        self._guardrail_hits: dict[int, list[dict[str, Any]]] = {}
        self._attach_sessions: dict[int, list[dict[str, Any]]] = {}
        self._port_allocations: dict[int, list[dict[str, Any]]] = {}
        self._service_endpoints: dict[int, list[dict[str, Any]]] = {}

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def upsert_runtime_queue_item(self, *, task_id: int, user_id: int, chat_id: int, query_text: str, **_: Any) -> None:
        self._tasks[task_id] = {
            "id": task_id,
            "user_id": user_id,
            "chat_id": chat_id,
            "query_text": query_text,
            "env_id": None,
        }

    def create_environment(self, *, task_id: int, classification: str, **kwargs: Any) -> int:
        env_id = self._id()
        env = {"id": env_id, "task_id": task_id, "classification": classification, **kwargs}
        self._environments[env_id] = env
        self._tasks[task_id]["env_id"] = env_id
        return env_id

    def add_event(self, *, task_id: int, event_type: str, **kwargs: Any) -> dict[str, Any]:
        event = {"id": self._id(), "seq": len(self._events.get(task_id, [])) + 1, "type": event_type, **kwargs}
        self._events.setdefault(task_id, []).append(event)
        return event

    def add_artifact(self, *, task_id: int, **kwargs: Any) -> int:
        artifact_id = self._id()
        self._artifacts.setdefault(task_id, []).append({"id": artifact_id, **kwargs})
        return artifact_id

    def add_browser_session(self, *, task_id: int, **kwargs: Any) -> int:
        session_id = self._id()
        self._browser_sessions.setdefault(task_id, []).append({"id": session_id, **kwargs})
        return session_id

    def add_loop_cycle(self, *, task_id: int, **kwargs: Any) -> int:
        cycle_id = self._id()
        self._loop_cycles.setdefault(task_id, []).append({"id": cycle_id, **kwargs})
        return cycle_id

    def add_guardrail_hit(self, *, task_id: int, **kwargs: Any) -> int:
        guardrail_id = self._id()
        self._guardrail_hits.setdefault(task_id, []).append({"id": guardrail_id, **kwargs})
        return guardrail_id

    def create_attach_session(self, *, task_id: int, **kwargs: Any) -> int:
        attach_id = self._id()
        self._attach_sessions.setdefault(task_id, []).append({"id": attach_id, **kwargs})
        return attach_id

    def add_port_allocation(self, *, task_id: int, **kwargs: Any) -> int:
        allocation_id = self._id()
        self._port_allocations.setdefault(task_id, []).append({"id": allocation_id, **kwargs})
        return allocation_id

    def add_service_endpoint(self, *, task_id: int, **kwargs: Any) -> int:
        endpoint_id = self._id()
        self._service_endpoints.setdefault(task_id, []).append({"id": endpoint_id, **kwargs})
        return endpoint_id

    def get_environment(self, env_id: int) -> dict[str, Any] | None:
        return self._environments.get(env_id)

    def get_task_runtime(self, task_id: int) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def list_artifacts(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._artifacts.get(task_id, []))

    def list_events(self, *, task_id: int) -> list[dict[str, Any]]:
        return list(self._events.get(task_id, []))

    def list_browser_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._browser_sessions.get(task_id, []))

    def list_loop_cycles(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._loop_cycles.get(task_id, []))

    def list_guardrail_hits(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._guardrail_hits.get(task_id, []))

    def list_attach_sessions(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._attach_sessions.get(task_id, []))

    def list_service_endpoints(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._service_endpoints.get(task_id, []))

    def list_port_allocations(self, task_id: int) -> list[dict[str, Any]]:
        return list(self._port_allocations.get(task_id, []))

    def list_runtime_queues(self) -> list[dict[str, Any]]:
        return [{"task_id": task_id} for task_id in self._tasks]


def test_runtime_store_round_trip_uses_postgres_delegate_surface():
    delegate = _RoundTripDelegate()
    with (
        patch("koda.services.runtime.store.postgres_primary_mode", return_value=True),
        patch("koda.services.runtime.store.get_primary_state_backend", return_value=object()),
        patch("koda.services.runtime.store.PostgresRuntimeStore", return_value=delegate),
    ):
        store = RuntimeStore()
        task_id = 41

        store.upsert_runtime_queue_item(task_id=task_id, user_id=111, chat_id=222, query_text="runtime task")
        env_id = store.create_environment(
            task_id=task_id,
            user_id=111,
            chat_id=222,
            classification="standard",
            environment_kind="dev_worktree",
            isolation="worktree",
            duration="medium",
            workspace_path="/tmp/runtime-workspace",
            runtime_dir="/tmp/runtime/task-1",
            base_work_dir="/tmp",
            branch_name="task/1-runtime-task",
            created_worktree=False,
            worktree_mode="shared_fallback",
            current_phase="planning",
        )

        event = store.add_event(
            task_id=task_id,
            env_id=env_id,
            attempt=1,
            phase="planning",
            event_type="task.classified",
            severity="info",
            payload={"classification": "standard"},
        )
        artifact_id = store.add_artifact(
            task_id=task_id,
            env_id=env_id,
            artifact_kind="log",
            label="stdout",
            path="/tmp/runtime/task-1/stdout/provider.log",
            metadata={"attempt": 1},
        )
        browser_session_id = store.add_browser_session(
            task_id=task_id,
            env_id=env_id,
            scope_id=task_id,
            transport="novnc",
            status="running",
            display_id=90,
            vnc_port=5901,
            novnc_port=6901,
            metadata={"novnc_url": "ws://127.0.0.1:6901"},
        )
        cycle_id = store.add_loop_cycle(
            task_id=task_id,
            env_id=env_id,
            cycle_index=1,
            phase="executing",
            plan={"step": "inspect"},
            outcome={"ok": True},
        )
        store.add_guardrail_hit(
            task_id=task_id,
            env_id=env_id,
            cycle_id=cycle_id,
            guardrail_type="repeated_command",
            details={"count": 3},
        )
        store.create_attach_session(
            task_id=task_id,
            env_id=env_id,
            attach_kind="terminal",
            terminal_id=None,
            token="token-123",
            can_write=True,
            actor="test",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        port_allocation_id = store.add_port_allocation(
            task_id=task_id,
            env_id=env_id,
            purpose="browser_novnc",
            host="127.0.0.1",
            port=6901,
            metadata={"service_kind": "browser_novnc"},
        )
        store.add_service_endpoint(
            task_id=task_id,
            env_id=env_id,
            process_id=None,
            service_kind="browser_novnc",
            label="Browser noVNC",
            host="127.0.0.1",
            port=6901,
            protocol="ws",
            url="ws://127.0.0.1:6901",
            metadata={"port_allocation_id": port_allocation_id},
        )

        env = store.get_environment(env_id)
        task = store.get_task_runtime(task_id)
        artifacts = store.list_artifacts(task_id)
        events = store.list_events(task_id=task_id)
        browser_sessions = store.list_browser_sessions(task_id)
        loop_cycles = store.list_loop_cycles(task_id)
        guardrail_hits = store.list_guardrail_hits(task_id)
        attach_sessions = store.list_attach_sessions(task_id)
        service_endpoints = store.list_service_endpoints(task_id)
        port_allocations = store.list_port_allocations(task_id)

    assert env is not None
    assert env["classification"] == "standard"
    assert task is not None
    assert task["env_id"] == env_id
    assert event["type"] == "task.classified"
    assert artifacts[0]["id"] == artifact_id
    assert events[0]["seq"] == event["seq"]
    assert browser_sessions[0]["id"] == browser_session_id
    assert loop_cycles[0]["id"] == cycle_id
    assert guardrail_hits[0]["guardrail_type"] == "repeated_command"
    assert attach_sessions[0]["token"] == "token-123"
    assert service_endpoints[0]["protocol"] == "ws"
    assert port_allocations[0]["port"] == 6901


def test_runtime_store_prefers_postgres_delegate_in_primary_mode():
    class _PrimaryDelegate:
        def __init__(self) -> None:
            self.called = False

        def list_runtime_queues(self) -> list[dict[str, int]]:
            self.called = True
            return [{"task_id": 7}]

    delegate = _PrimaryDelegate()
    with (
        patch("koda.services.runtime.store.postgres_primary_mode", return_value=True),
        patch("koda.services.runtime.store.get_primary_state_backend", return_value=object()),
        patch("koda.services.runtime.store.PostgresRuntimeStore", return_value=delegate),
    ):
        store = RuntimeStore()
        rows = store.list_runtime_queues()

    assert rows == [{"task_id": 7}]
    assert delegate.called is True


def test_runtime_store_has_no_legacy_delegate():
    import koda.services.runtime.store as runtime_store_module

    assert not hasattr(runtime_store_module, "_SqliteRuntimeStore")
