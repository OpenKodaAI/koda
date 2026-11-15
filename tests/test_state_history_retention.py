"""The daily retention report degrades to a warning when Postgres is unavailable (D-053)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_run_maintenance_reports_an_unavailable_backend_as_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily loop logs the result; an unavailable backend must come back as
    an ``error`` entry with the ``db_maintenance_error`` warning, not as an
    exception the loop logs with a trace."""
    from koda.state import history_store

    def _unavailable(**_kwargs: object) -> None:
        raise RuntimeError("history_primary_backend_unavailable")

    log = MagicMock()
    monkeypatch.setattr(history_store, "log", log)
    monkeypatch.setattr(history_store, "postgres_primary_mode", lambda: True)
    monkeypatch.setattr(history_store, "require_primary_state_backend", _unavailable)

    result = history_store.run_maintenance()

    assert result["mode"] == "report_only"
    assert result["error"] == "history_primary_backend_unavailable"
    log.warning.assert_called_once_with("db_maintenance_error", error="history_primary_backend_unavailable")
