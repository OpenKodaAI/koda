"""The approval-grant store has one backend, Postgres; without it every call fails visibly (M2-E1-T2).

Round trips against a real database are in tests/test_state_approval_stores_postgres.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from koda.state import approval_grants

pytestmark = [pytest.mark.real_approval_store]


@pytest.fixture(autouse=True)
def _no_primary_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import koda.config as config_module

    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(approval_grants, "get_primary_state_backend", lambda **_kwargs: None)
    log = MagicMock()
    monkeypatch.setattr(approval_grants, "log", log)
    return log


@pytest.mark.parametrize(
    "call",
    [
        lambda: approval_grants.save_approval_grant("grant-1", {"user_id": 42, "agent_id": "AGENT_A"}, 300),
        lambda: approval_grants.update_approval_grant("grant-1", {"user_id": 42, "agent_id": "AGENT_A"}),
        lambda: approval_grants.remove_approval_grant("grant-1", agent_id="AGENT_A"),
        lambda: approval_grants.remove_approval_grants(agent_id="AGENT_A", user_id=42),
        lambda: approval_grants.cleanup_expired_approval_grants(),
        lambda: approval_grants.load_approval_grants(agent_id="AGENT_A"),
    ],
    ids=["save", "update", "remove", "remove_matching", "cleanup", "load"],
)
async def test_without_postgres_each_call_raises_is_logged_and_writes_no_file(
    call, tmp_path: Path, _no_primary_backend: MagicMock
) -> None:
    with pytest.raises(RuntimeError, match="approval_grants_primary_backend_unavailable"):
        await call()

    assert _no_primary_backend.exception.called
    assert list(tmp_path.iterdir()) == []


async def test_outside_postgres_mode_each_write_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import koda.config as config_module

    monkeypatch.setattr(config_module, "STATE_BACKEND", "sqlite")
    with pytest.raises(RuntimeError, match="approval_grants_primary_mode_required"):
        await approval_grants.save_approval_grant("grant-1", {"user_id": 42, "agent_id": "AGENT_A"}, 300)
    assert list(tmp_path.iterdir()) == []
