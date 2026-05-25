from __future__ import annotations

import json
from unittest.mock import MagicMock

from koda.control_plane.manager import ControlPlaneManager
from koda.state import dashboard_store
from koda.state.dashboard_store import DashboardStore


def _install_dashboard_fetch(
    monkeypatch,
    *,
    session_rows: list[dict],
    query_aggs: list[dict],
    latest_queries: list[dict],
    task_aggs: list[dict],
    latest_tasks: list[dict],
    session_queries: dict[str, list[dict]] | None = None,
    session_tasks: dict[str, list[dict]] | None = None,
    runtime_artifacts: dict[int, list[dict]] | None = None,
    audit_by_task: dict[int, list[dict]] | None = None,
    normalized_scope: str | None = None,
) -> DashboardStore:
    session_queries = session_queries or {}
    session_tasks = session_tasks or {}
    runtime_artifacts = runtime_artifacts or {}
    audit_by_task = audit_by_task or {}

    def fake_fetch_all(agent_id: str, query: str, params: tuple = ()):
        normalized_query = " ".join(query.split())
        if "FROM sessions" in normalized_query and "WHERE agent_id = ? AND session_id IS NOT NULL" in normalized_query:
            return session_rows
        if "COUNT(*) AS query_count" in normalized_query and "FROM query_history" in normalized_query:
            return query_aggs
        if "SELECT DISTINCT ON (session_id)" in normalized_query and "FROM query_history" in normalized_query:
            return latest_queries
        if "COUNT(*) AS execution_count" in normalized_query and "FROM tasks" in normalized_query:
            return task_aggs
        if "id AS task_id" in normalized_query and "FROM tasks" in normalized_query:
            return latest_tasks
        if "FROM query_history WHERE agent_id = ? AND session_id = ?" in normalized_query:
            return session_queries.get(str(params[1]), [])
        if "FROM tasks" in normalized_query and "WHERE agent_id = ? AND session_id = ?" in normalized_query:
            return session_tasks.get(str(params[1]), [])
        if "FROM runtime_artifacts" in normalized_query and "task_id = ?" in normalized_query:
            rows = runtime_artifacts.get(int(params[1]), [])
            requested_agent = str(params[0])
            if "LOWER(agent_id) = LOWER(?)" in normalized_query:
                return [
                    row
                    for row in rows
                    if str(row.get("agent_id") or requested_agent).lower() == requested_agent.lower()
                ]
            return [row for row in rows if str(row.get("agent_id") or requested_agent) == requested_agent]
        raise AssertionError(f"Unhandled dashboard fetch: {normalized_query}")

    monkeypatch.setattr(
        dashboard_store,
        "_normalize_scope",
        lambda agent_id: normalized_scope if normalized_scope is not None else str(agent_id).lower(),
    )
    monkeypatch.setattr(dashboard_store, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        DashboardStore,
        "_audit_events_for_tasks",
        lambda self, agent_id, task_ids: {task_id: audit_by_task.get(task_id, []) for task_id in task_ids},
    )
    return DashboardStore()


def test_list_sessions_groups_multiple_messages_under_one_session(monkeypatch) -> None:
    store = _install_dashboard_fetch(
        monkeypatch,
        session_rows=[
            {
                "session_id": "session-shared",
                "name": "Shared",
                "user_id": 1,
                "created_at": "2026-03-28T09:00:00.000Z",
                "last_used": "2026-03-28T09:10:00.000Z",
            }
        ],
        query_aggs=[
            {
                "session_id": "session-shared",
                "query_count": 2,
                "total_cost_usd": 0.3,
                "last_query_at": "2026-03-28T09:10:00.000Z",
            }
        ],
        latest_queries=[
            {
                "session_id": "session-shared",
                "user_id": 1,
                "timestamp": "2026-03-28T09:10:00.000Z",
                "query_text": "Second",
                "response_text": "Second answer",
                "model": "claude-opus-4-6",
                "error": False,
            }
        ],
        task_aggs=[
            {
                "session_id": "session-shared",
                "execution_count": 2,
                "total_cost_usd": 0.3,
                "running_count": 0,
                "failed_count": 0,
                "last_execution_at": "2026-03-28T09:10:00.000Z",
            }
        ],
        latest_tasks=[
            {
                "task_id": 22,
                "session_id": "session-shared",
                "user_id": 1,
                "status": "completed",
                "query_text": "Second",
                "activity_at": "2026-03-28T09:10:00.000Z",
            }
        ],
    )

    items = store.list_sessions("backend_developer")

    assert len(items) == 1
    assert items[0]["session_id"] == "session-shared"
    assert items[0]["query_count"] == 2
    assert items[0]["execution_count"] == 2


def test_list_sessions_hides_sessions_without_recoverable_preview(monkeypatch) -> None:
    store = _install_dashboard_fetch(
        monkeypatch,
        session_rows=[
            {
                "session_id": "session-empty",
                "name": "Invisible",
                "user_id": 1,
                "created_at": "2026-03-28T10:00:00.000Z",
                "last_used": "2026-03-28T10:05:00.000Z",
            }
        ],
        query_aggs=[],
        latest_queries=[],
        task_aggs=[
            {
                "session_id": "session-empty",
                "execution_count": 1,
                "total_cost_usd": 0.0,
                "running_count": 0,
                "failed_count": 0,
                "last_execution_at": "2026-03-28T10:05:00.000Z",
            }
        ],
        latest_tasks=[
            {
                "task_id": 11,
                "session_id": "session-empty",
                "user_id": 1,
                "status": "completed",
                "query_text": None,
                "activity_at": "2026-03-28T10:05:00.000Z",
            }
        ],
    )

    assert store.list_sessions("backend_developer") == []


def test_get_session_synthesizes_execution_backed_transcript(monkeypatch) -> None:
    store = _install_dashboard_fetch(
        monkeypatch,
        session_rows=[
            {
                "session_id": "session-gamma",
                "name": None,
                "user_id": 1,
                "created_at": "2026-03-28T08:40:00.000Z",
                "last_used": "2026-03-28T08:42:00.000Z",
            }
        ],
        query_aggs=[],
        latest_queries=[],
        task_aggs=[
            {
                "session_id": "session-gamma",
                "execution_count": 1,
                "total_cost_usd": 0.09,
                "running_count": 0,
                "failed_count": 0,
                "last_execution_at": "2026-03-28T08:42:00.000Z",
            }
        ],
        latest_tasks=[
            {
                "task_id": 7,
                "session_id": "session-gamma",
                "user_id": 1,
                "status": "completed",
                "query_text": "Bom dia",
                "activity_at": "2026-03-28T08:42:00.000Z",
            }
        ],
        session_tasks={
            "session-gamma": [
                {
                    "id": 7,
                    "agent_id": "backend_developer",
                    "status": "completed",
                    "query_text": "Bom dia",
                    "model": "claude-opus-4-6",
                    "session_id": "session-gamma",
                    "user_id": 1,
                    "chat_id": 99,
                    "created_at": "2026-03-28T08:42:00.000Z",
                    "started_at": "2026-03-28T08:42:01.000Z",
                    "completed_at": "2026-03-28T08:42:03.000Z",
                    "cost_usd": 0.09,
                    "attempt": 1,
                    "max_attempts": 1,
                    "error_message": None,
                    "work_dir": "/tmp/session-gamma",
                }
            ]
        },
    )

    detail = store.get_session("backend_developer", "session-gamma")

    assert detail is not None
    # dashboard_store now normalizes to uppercase to match cp_agent_definitions.id
    # and the rest of the dashboard API. Both agent_id + bot_id are emitted.
    assert detail["summary"]["bot_id"] == "BACKEND_DEVELOPER"
    assert detail["summary"]["agent_id"] == "BACKEND_DEVELOPER"
    assert [message["role"] for message in detail["messages"]] == ["user"]
    assert detail["messages"][0]["text"] == "Bom dia"
    assert detail["messages"][0]["linked_execution"]["task_id"] == 7


def test_get_session_includes_telegram_execution_artifacts(monkeypatch) -> None:
    store = _install_dashboard_fetch(
        monkeypatch,
        session_rows=[
            {
                "session_id": "session-telegram",
                "name": None,
                "user_id": 42,
                "created_at": "2026-03-28T10:00:00.000Z",
                "last_used": "2026-03-28T10:05:00.000Z",
            }
        ],
        query_aggs=[
            {
                "session_id": "session-telegram",
                "query_count": 1,
                "total_cost_usd": 0.2,
                "last_query_at": "2026-03-28T10:05:00.000Z",
            }
        ],
        latest_queries=[
            {
                "session_id": "session-telegram",
                "user_id": 42,
                "timestamp": "2026-03-28T10:05:00.000Z",
                "query_text": "Gere uma imagem",
                "response_text": "Pronto, gerei a imagem.",
                "model": "gpt-5.4-mini",
                "error": False,
            }
        ],
        task_aggs=[
            {
                "session_id": "session-telegram",
                "execution_count": 1,
                "total_cost_usd": 0.2,
                "running_count": 0,
                "failed_count": 0,
                "last_execution_at": "2026-03-28T10:05:00.000Z",
            }
        ],
        latest_tasks=[
            {
                "task_id": 31,
                "session_id": "session-telegram",
                "user_id": 42,
                "status": "completed",
                "query_text": "Gere uma imagem",
                "activity_at": "2026-03-28T10:05:00.000Z",
            }
        ],
        session_queries={
            "session-telegram": [
                {
                    "id": 5,
                    "user_id": 42,
                    "timestamp": "2026-03-28T10:05:00.000Z",
                    "query_text": "Gere uma imagem",
                    "response_text": "Pronto, gerei a imagem.",
                    "cost_usd": 0.2,
                    "model": "gpt-5.4-mini",
                    "session_id": "session-telegram",
                    "error": False,
                }
            ]
        },
        session_tasks={
            "session-telegram": [
                {
                    "id": 31,
                    "agent_id": "backend_developer",
                    "status": "completed",
                    "query_text": "Gere uma imagem",
                    "model": "gpt-5.4-mini",
                    "session_id": "session-telegram",
                    "user_id": 42,
                    "chat_id": 99,
                    "created_at": "2026-03-28T10:04:58.000Z",
                    "started_at": "2026-03-28T10:05:00.000Z",
                    "completed_at": "2026-03-28T10:05:10.000Z",
                    "cost_usd": 0.2,
                    "attempt": 1,
                    "max_attempts": 1,
                    "error_message": None,
                    "work_dir": "/tmp/session-telegram",
                }
            ]
        },
        runtime_artifacts={
            31: [
                {
                    "id": 77,
                    "task_id": 31,
                    "env_id": None,
                    "artifact_kind": "image",
                    "label": "generated.png",
                    "path": "/tmp/session-telegram/generated.png",
                    "metadata_json": json.dumps(
                        {
                            "mime_type": "image/png",
                            "size_bytes": 123,
                            "source_type": "provider_output",
                        }
                    ),
                    "created_at": "2026-03-28T10:05:10.000Z",
                    "expires_at": None,
                },
                {
                    "id": 78,
                    "task_id": 31,
                    "env_id": None,
                    "artifact_kind": "audio",
                    "label": "voice-response-31.ogg",
                    "path": "/tmp/session-telegram/voice-response-31.ogg",
                    "metadata_json": json.dumps(
                        {
                            "mime_type": "audio/ogg",
                            "size_bytes": 456,
                            "source_type": "voice_response",
                            "voice": "pm_alex",
                        }
                    ),
                    "created_at": "2026-03-28T10:05:11.000Z",
                    "expires_at": None,
                },
            ]
        },
        audit_by_task={
            31: [
                {
                    "id": 88,
                    "timestamp": "2026-03-28T10:05:10.000Z",
                    "event_type": "task.execution_trace",
                    "details_json": json.dumps(
                        {
                            "schema": "execution_trace",
                            "request": {"query_text": "Gere uma imagem", "session_id": "session-telegram"},
                            "assistant": {"response_text": "Pronto, gerei a imagem."},
                            "runtime": {"stop_reason": "completed"},
                            "tools": [],
                        }
                    ),
                }
            ]
        },
    )

    detail = store.get_session("backend_developer", "session-telegram")

    assert detail is not None
    assistant_message = next(message for message in detail["messages"] if message["role"] == "assistant")
    assert assistant_message["linked_execution"]["task_id"] == 31
    assert assistant_message["artifacts"][0]["id"] == "77"
    assert assistant_message["artifacts"][0]["metadata"]["runtime_artifact_id"] == "77"
    voice_artifact = next(artifact for artifact in assistant_message["artifacts"] if artifact["kind"] == "audio")
    assert voice_artifact["id"] == "78"
    assert voice_artifact["source_type"] == "voice_response"
    assert voice_artifact["metadata"]["runtime_artifact_id"] == "78"
    assert voice_artifact["metadata"]["source_execution_id"] == "31"


def test_get_session_reads_runtime_artifacts_case_insensitively_for_artifact_only_message(monkeypatch) -> None:
    store = _install_dashboard_fetch(
        monkeypatch,
        normalized_scope="KODA",
        session_rows=[
            {
                "session_id": "session-case",
                "name": None,
                "user_id": 42,
                "created_at": "2026-05-06T04:00:00.000Z",
                "last_used": "2026-05-06T04:03:00.000Z",
            }
        ],
        query_aggs=[
            {
                "session_id": "session-case",
                "query_count": 1,
                "total_cost_usd": 0.2,
                "last_query_at": "2026-05-06T04:03:00.000Z",
            }
        ],
        latest_queries=[
            {
                "session_id": "session-case",
                "user_id": 42,
                "timestamp": "2026-05-06T04:03:00.000Z",
                "query_text": "Gere uma imagem",
                "response_text": "",
                "model": "gpt-5.4-mini",
                "error": False,
            }
        ],
        task_aggs=[
            {
                "session_id": "session-case",
                "execution_count": 1,
                "total_cost_usd": 0.2,
                "running_count": 0,
                "failed_count": 0,
                "last_execution_at": "2026-05-06T04:03:10.000Z",
            }
        ],
        latest_tasks=[
            {
                "task_id": 453,
                "session_id": "session-case",
                "user_id": 42,
                "status": "completed",
                "query_text": "Gere uma imagem",
                "activity_at": "2026-05-06T04:03:10.000Z",
            }
        ],
        session_queries={
            "session-case": [
                {
                    "id": 45,
                    "user_id": 42,
                    "timestamp": "2026-05-06T04:03:00.000Z",
                    "query_text": "Gere uma imagem",
                    "response_text": "",
                    "cost_usd": 0.2,
                    "model": "gpt-5.4-mini",
                    "session_id": "session-case",
                    "error": False,
                }
            ]
        },
        session_tasks={
            "session-case": [
                {
                    "id": 453,
                    "agent_id": "KODA",
                    "status": "completed",
                    "query_text": "Gere uma imagem",
                    "model": "gpt-5.4-mini",
                    "session_id": "session-case",
                    "user_id": 42,
                    "chat_id": 99,
                    "created_at": "2026-05-06T04:02:58.000Z",
                    "started_at": "2026-05-06T04:03:00.000Z",
                    "completed_at": "2026-05-06T04:03:10.000Z",
                    "cost_usd": 0.2,
                    "attempt": 1,
                    "max_attempts": 1,
                    "error_message": None,
                    "work_dir": "/tmp/session-case",
                }
            ]
        },
        runtime_artifacts={
            453: [
                {
                    "id": 428,
                    "agent_id": "koda",
                    "task_id": 453,
                    "env_id": None,
                    "artifact_kind": "image",
                    "label": "generated.png",
                    "path": "/tmp/session-case/generated.png",
                    "metadata_json": json.dumps(
                        {
                            "mime_type": "image/png",
                            "size_bytes": 123,
                            "source_type": "provider_output",
                        }
                    ),
                    "created_at": "2026-05-06T04:03:10.000Z",
                    "expires_at": None,
                },
                {
                    "id": 429,
                    "agent_id": "koda",
                    "task_id": 453,
                    "env_id": None,
                    "artifact_kind": "audio",
                    "label": "voice-response-453.ogg",
                    "path": "/tmp/session-case/voice-response-453.ogg",
                    "metadata_json": json.dumps(
                        {
                            "mime_type": "audio/ogg",
                            "size_bytes": 456,
                            "source_type": "voice_response",
                        }
                    ),
                    "created_at": "2026-05-06T04:03:11.000Z",
                    "expires_at": None,
                },
            ]
        },
        audit_by_task={
            453: [
                {
                    "id": 901,
                    "timestamp": "2026-05-06T04:03:10.000Z",
                    "event_type": "task.execution_trace",
                    "details_json": json.dumps(
                        {
                            "schema": "execution_trace",
                            "request": {"query_text": "Gere uma imagem", "session_id": "session-case"},
                            "assistant": {"response_text": ""},
                            "runtime": {"stop_reason": "completed"},
                            "tools": [],
                        }
                    ),
                }
            ]
        },
    )

    detail = store.get_session("KODA", "session-case")

    assert detail is not None
    assistant_message = next(message for message in detail["messages"] if message["role"] == "assistant")
    assert assistant_message["text"] == ""
    assert assistant_message["linked_execution"]["task_id"] == 453
    assert [artifact["id"] for artifact in assistant_message["artifacts"]] == ["428", "429"]
    assert {artifact["kind"] for artifact in assistant_message["artifacts"]} == {"image", "audio"}


def test_get_session_cursor_pagination_is_stable(monkeypatch) -> None:
    query_rows = [
        {
            "id": 1,
            "user_id": 1,
            "timestamp": "2026-03-28T09:00:00.000Z",
            "query_text": "First",
            "response_text": "First answer",
            "cost_usd": 0.1,
            "model": "claude-opus-4-6",
            "session_id": "session-alpha",
            "error": False,
        },
        {
            "id": 2,
            "user_id": 1,
            "timestamp": "2026-03-28T09:05:00.000Z",
            "query_text": "Second",
            "response_text": "Second answer",
            "cost_usd": 0.1,
            "model": "claude-opus-4-6",
            "session_id": "session-alpha",
            "error": False,
        },
        {
            "id": 3,
            "user_id": 1,
            "timestamp": "2026-03-28T09:10:00.000Z",
            "query_text": "Third",
            "response_text": "Third answer",
            "cost_usd": 0.1,
            "model": "claude-opus-4-6",
            "session_id": "session-alpha",
            "error": False,
        },
    ]
    store = _install_dashboard_fetch(
        monkeypatch,
        session_rows=[
            {
                "session_id": "session-alpha",
                "name": "Alpha",
                "user_id": 1,
                "created_at": "2026-03-28T09:00:00.000Z",
                "last_used": "2026-03-28T09:10:00.000Z",
            }
        ],
        query_aggs=[
            {
                "session_id": "session-alpha",
                "query_count": 3,
                "total_cost_usd": 0.3,
                "last_query_at": "2026-03-28T09:10:00.000Z",
            }
        ],
        latest_queries=[query_rows[-1]],
        task_aggs=[],
        latest_tasks=[],
        session_queries={"session-alpha": query_rows},
    )

    first_page = store.get_session("backend_developer", "session-alpha", limit=2)
    assert first_page is not None
    assert first_page["page"]["has_more"] is True
    assert [message["id"] for message in first_page["messages"]] == [
        "query-2-user",
        "query-2-assistant",
        "query-3-user",
        "query-3-assistant",
    ]

    second_page = store.get_session(
        "backend_developer",
        "session-alpha",
        limit=2,
        before=first_page["page"]["next_cursor"],
    )
    assert second_page is not None
    assert [message["id"] for message in second_page["messages"]] == [
        "query-1-user",
        "query-1-assistant",
    ]
    assert set(message["id"] for message in second_page["messages"]).isdisjoint(
        {message["id"] for message in first_page["messages"]}
    )


def test_manager_dedupes_normalized_agent_ids_in_global_session_list(monkeypatch) -> None:
    manager = object.__new__(ControlPlaneManager)
    store = MagicMock()
    store.list_sessions.return_value = [
        {
            "bot_id": "BACKEND_DEVELOPER",
            "session_id": "session-1",
            "last_activity_at": "2026-03-28T09:10:00.000Z",
        }
    ]
    monkeypatch.setattr(manager, "_require_dashboard_agent", lambda agent_id: (str(agent_id).lower(), {}))
    monkeypatch.setattr(manager, "_dashboard_store", lambda: store)

    payload = manager.list_dashboard_session_summaries(
        agent_ids=["backend_developer", "BACKEND_DEVELOPER"],
        limit=20,
        offset=0,
    )

    assert payload == [
        {
            "bot_id": "BACKEND_DEVELOPER",
            "session_id": "session-1",
            "last_activity_at": "2026-03-28T09:10:00.000Z",
        }
    ]
    store.list_sessions.assert_called_once()
