from __future__ import annotations

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
    audit_by_task: dict[int, list[dict]] | None = None,
) -> DashboardStore:
    session_queries = session_queries or {}
    session_tasks = session_tasks or {}
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
        raise AssertionError(f"Unhandled dashboard fetch: {normalized_query}")

    monkeypatch.setattr(dashboard_store, "_normalize_scope", lambda agent_id: str(agent_id).lower())
    monkeypatch.setattr(dashboard_store, "_fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        DashboardStore,
        "_audit_events_for_tasks",
        lambda self, agent_id, task_ids: {task_id: audit_by_task.get(task_id, []) for task_id in task_ids},
    )
    return DashboardStore()


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
    assert detail["summary"]["bot_id"] == "backend_developer"
    assert [message["role"] for message in detail["messages"]] == ["user"]
    assert detail["messages"][0]["text"] == "Bom dia"
    assert detail["messages"][0]["linked_execution"]["task_id"] == 7


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
