"""The pending-approval store has one backend, Postgres; without it every call fails visibly (M2-E1-T2).

Round trips against a real database are in tests/test_state_approval_stores_postgres.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from koda.state import pending_approvals

pytestmark = [pytest.mark.real_approval_store]


@pytest.fixture(autouse=True)
def _no_primary_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    import koda.config as config_module

    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)
    monkeypatch.setattr(pending_approvals, "get_primary_state_backend", lambda **_kwargs: None)
    log = MagicMock()
    monkeypatch.setattr(pending_approvals, "log", log)
    return log


@pytest.mark.parametrize(
    "call",
    [
        lambda: pending_approvals.save_pending_op("op1", {"user_id": 42, "op_type": "user"}, ttl_seconds=300),
        lambda: pending_approvals.remove_pending_op("op1", agent_id="AGENT_A"),
        lambda: pending_approvals.remove_pending_ops(user_id=42),
        lambda: pending_approvals.cleanup_expired_ops(),
        lambda: pending_approvals.expire_pending_ops(agent_id="AGENT_A", created_before=0.0),
    ],
    ids=["save", "remove", "remove_matching", "cleanup", "expire"],
)
async def test_without_postgres_each_call_raises_is_logged_and_writes_no_file(
    call, tmp_path: Path, _no_primary_backend: MagicMock
) -> None:
    with pytest.raises(RuntimeError, match="pending_approvals_primary_backend_unavailable"):
        await call()

    assert _no_primary_backend.exception.called
    assert list(tmp_path.iterdir()) == []


async def test_removing_with_no_filter_removes_nothing() -> None:
    assert await pending_approvals.remove_pending_ops() == 0
