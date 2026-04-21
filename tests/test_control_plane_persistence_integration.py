"""Integration tests for the persistence fail-loud guardrails.

These tests exercise the three defenses that keep "save appears to work but
nothing persisted" from silently happening:

* **Layer A** — :func:`koda.state.primary.primary_execute` (and friends)
  raise instead of returning empty sentinels when the backend is absent and
  the system is in ``STATE_BACKEND=postgres`` mode.
* **Layer C** — :meth:`ControlPlaneManager._persist_global_sections` reads
  back the rows it just wrote and raises when they are missing.
* **Layer E** — :meth:`ControlPlaneManager.get_persistence_diagnostics`
  reports the real backend state so an operator can curl and see what is
  wrong.
"""

from __future__ import annotations

import asyncio

import pytest

import koda.control_plane.manager as manager_mod
import koda.state.primary as state_primary

# ---------------------------------------------------------------------------
# Layer A — primary_execute / fetch_* fail-loud when backend is unavailable.
# ---------------------------------------------------------------------------


def test_primary_execute_raises_when_backend_missing_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    with pytest.raises(RuntimeError, match="primary_backend_unavailable: execute"):
        asyncio.run(state_primary.primary_execute("INSERT INTO cp_global_sections VALUES (?)", ("x",)))


def test_primary_fetch_all_raises_when_backend_missing_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    with pytest.raises(RuntimeError, match="primary_backend_unavailable: fetch_all"):
        asyncio.run(state_primary.primary_fetch_all("SELECT 1"))


def test_primary_fetch_one_raises_when_backend_missing_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    with pytest.raises(RuntimeError, match="primary_backend_unavailable: fetch_one"):
        asyncio.run(state_primary.primary_fetch_one("SELECT 1"))


def test_primary_fetch_val_raises_when_backend_missing_in_postgres_mode(monkeypatch):
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    with pytest.raises(RuntimeError, match="primary_backend_unavailable: fetch_val"):
        asyncio.run(state_primary.primary_fetch_val("SELECT 1"))


def test_primary_execute_is_quiet_when_not_in_postgres_mode(monkeypatch):
    """Non-postgres modes (legacy / test-only) keep the empty-sentinel return
    so existing caller code does not break."""
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: False)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    assert asyncio.run(state_primary.primary_execute("NOOP")) == 0
    assert asyncio.run(state_primary.primary_fetch_all("SELECT 1")) == []
    assert asyncio.run(state_primary.primary_fetch_one("SELECT 1")) is None
    assert asyncio.run(state_primary.primary_fetch_val("SELECT 1")) is None


# ---------------------------------------------------------------------------
# Layer C — post-write verify in _persist_global_sections.
# ---------------------------------------------------------------------------


def _manager() -> manager_mod.ControlPlaneManager:
    return manager_mod.ControlPlaneManager.__new__(manager_mod.ControlPlaneManager)


def test_persist_global_sections_raises_when_rows_are_lost(monkeypatch):
    """Simulates a silent DB failure: execute returns success but the row is
    never visible on read. Persist must raise, not pretend success."""
    manager = _manager()
    persisted_calls: list[tuple[str, tuple]] = []

    def _execute(query, params=()):
        persisted_calls.append((query, params))
        return 1

    # _load_global_sections returns {} — simulating the silent-failure scenario
    # where execute was a no-op and nothing was written.
    manager._load_global_sections = lambda: {}  # type: ignore[attr-defined]
    manager._persist_global_default_version = lambda sections: 1  # type: ignore[attr-defined]

    monkeypatch.setattr(manager_mod, "execute", _execute)
    monkeypatch.setattr(manager_mod, "now_iso", lambda: "2026-04-20T00:00:00Z")

    with pytest.raises(RuntimeError, match="persist_global_sections_lost"):
        manager_mod.ControlPlaneManager._persist_global_sections(
            manager, {"memory": {"env": {"MEMORY_ENABLED": "true"}}}
        )
    assert persisted_calls, "expected execute to have been called"


def test_persist_global_sections_passes_when_rows_are_visible(monkeypatch):
    manager = _manager()

    def _execute(query, params=()):
        return 1

    # _load_global_sections returns the section we wrote — persist succeeds.
    manager._load_global_sections = lambda: {"memory": {"env": {"MEMORY_ENABLED": "true"}}}  # type: ignore[attr-defined]
    manager._persist_global_default_version = lambda sections: 7  # type: ignore[attr-defined]

    monkeypatch.setattr(manager_mod, "execute", _execute)
    monkeypatch.setattr(manager_mod, "now_iso", lambda: "2026-04-20T00:00:00Z")

    version = manager_mod.ControlPlaneManager._persist_global_sections(
        manager, {"memory": {"env": {"MEMORY_ENABLED": "true"}}}
    )
    assert version == 7


# ---------------------------------------------------------------------------
# Layer E — diagnostics endpoint exposes real state.
# ---------------------------------------------------------------------------


def test_diagnostics_reports_backend_unavailable(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: None)
    monkeypatch.setattr(manager_mod, "fetch_one", lambda *args, **kwargs: None)

    diag = manager_mod.ControlPlaneManager.get_persistence_diagnostics(manager)
    assert diag["postgres_primary_mode"] is True
    assert diag["primary_backend_available"] is False
    assert any("STATE_BACKEND=postgres" in w for w in diag["warnings"]), diag["warnings"]
    assert diag["row_counts"]["cp_global_sections"] == 0


def test_diagnostics_reports_row_counts_and_last_write(monkeypatch):
    manager = _manager()

    class _FakeBackend:
        schema = "koda"

    monkeypatch.setattr(state_primary, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(state_primary, "get_primary_state_backend", lambda **_: _FakeBackend())

    responses = {
        "SELECT COUNT(*) AS count FROM cp_global_sections": {"count": 7},
        "SELECT COUNT(*) AS count FROM cp_provider_connections": {"count": 4},
        "SELECT COUNT(*) AS count FROM cp_secret_values": {"count": 2},
        "SELECT COUNT(*) AS count FROM cp_agent_definitions": {"count": 1},
        "SELECT MAX(updated_at) AS updated_at FROM cp_global_sections": {"updated_at": "2026-04-20T16:58:00Z"},
    }
    monkeypatch.setattr(manager_mod, "fetch_one", lambda query, params=(): responses.get(query.strip()))

    diag = manager_mod.ControlPlaneManager.get_persistence_diagnostics(manager)
    assert diag["primary_backend_available"] is True
    assert diag["postgres_schema"] == "koda"
    assert diag["row_counts"]["cp_global_sections"] == 7
    assert diag["row_counts"]["cp_provider_connections"] == 4
    assert diag["row_counts"]["cp_secret_values"] == 2
    assert diag["last_updated_at"] == "2026-04-20T16:58:00Z"
    assert diag["warnings"] == []
