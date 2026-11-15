"""An audit event the primary backend does not write is logged, not lost silently."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


class _Backend:
    def __init__(self, *, bootstrapped: bool, starts: bool = True) -> None:
        self.bootstrapped = bootstrapped
        self._starts = starts
        self.started = 0
        self.persisted: list[dict[str, Any]] = []

    async def start(self) -> bool:
        self.started += 1
        self.bootstrapped = self._starts
        return self._starts

    async def persist_audit_event(self, **kwargs: Any) -> int | None:
        if not self.bootstrapped:
            return None
        self.persisted.append(kwargs)
        return 1


def _insert(monkeypatch: pytest.MonkeyPatch, backend: _Backend) -> MagicMock:
    from koda.services import audit

    log = MagicMock()
    monkeypatch.setattr(audit, "log", log)
    monkeypatch.setattr(audit, "_primary_audit_backend", lambda: backend)
    audit._insert_audit(audit.AuditEvent(event_type="retention.report"))
    return log


def test_a_fresh_backend_is_started_before_the_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    """On a transient loop the shared backend is fresh; it is bootstrapped first,
    since ``persist_audit_event`` writes nothing on an unbootstrapped backend."""
    backend = _Backend(bootstrapped=False)

    log = _insert(monkeypatch, backend)

    assert backend.started == 1
    assert [row["event_type"] for row in backend.persisted] == ["retention.report"]
    log.warning.assert_not_called()


def test_an_event_that_is_not_written_logs_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _Backend(bootstrapped=False, starts=False)

    log = _insert(monkeypatch, backend)

    assert backend.persisted == []
    assert log.warning.call_args.args == ("audit_primary_insert_failed",)
    assert log.warning.call_args.kwargs["event_type"] == "retention.report"
