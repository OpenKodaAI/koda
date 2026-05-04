from __future__ import annotations

from unittest.mock import patch

from koda.memory.napkin import get_exact_linked_memories, get_expired_active, search_entries_lexical


def test_lexical_search_filters_invalid_windows() -> None:
    with patch("koda.memory.napkin._fetch_rows", return_value=[]) as fetch_rows:
        search_entries_lexical(user_id=111, query="deploy rollback", agent_id="agent_a")

    sql, params = fetch_rows.call_args.args
    assert "expires_at >= ?" in sql
    assert "valid_until >= ?" in sql
    assert len(params) >= 5


def test_exact_linked_search_filters_invalid_windows() -> None:
    with patch("koda.memory.napkin._fetch_rows", return_value=[]) as fetch_rows:
        get_exact_linked_memories(user_id=111, agent_id="agent_a", source_task_id=42)

    sql, params = fetch_rows.call_args.args
    assert "expires_at >= ?" in sql
    assert "valid_until >= ?" in sql
    assert 42 in params


def test_expired_active_includes_valid_until() -> None:
    with patch("koda.memory.napkin._fetch_rows", return_value=[]) as fetch_rows:
        get_expired_active("2026-05-04T10:00:00", agent_id="agent_a")

    sql, params = fetch_rows.call_args.args
    assert "valid_until" in sql
    assert params[-1] == "2026-05-04T10:00:00"
