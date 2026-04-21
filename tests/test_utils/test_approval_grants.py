"""Tests for the scoped approval-grants persistence layer."""

from __future__ import annotations

import json
import time

import pytest

from koda.state.approval_grants import (
    cleanup_expired_approval_grants,
    load_approval_grants,
    remove_approval_grant,
    replace_approval_grants,
    save_approval_grant,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    import koda.config as config_module

    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)


@pytest.mark.asyncio
async def test_save_and_load_round_trip():
    await save_approval_grant(
        "grant-1",
        {
            "user_id": 42,
            "agent_id": "agent-a",
            "kind": "approve_scope",
            "remaining_uses": 10,
            "max_uses": 10,
        },
        ttl_seconds=300,
    )

    grants = await load_approval_grants()
    assert grants["grant-1"]["user_id"] == 42
    assert grants["grant-1"]["agent_id"] == "agent-a"
    assert grants["grant-1"]["remaining_uses"] == 10
    assert grants["grant-1"]["expires_at"] > grants["grant-1"]["created_at"]


@pytest.mark.asyncio
async def test_replace_and_remove_round_trip():
    await replace_approval_grants(
        {
            "grant-2": {
                "grant_id": "grant-2",
                "user_id": 9,
                "agent_id": "agent-b",
                "remaining_uses": 2,
                "expires_at": time.time() + 60,
            }
        }
    )
    assert "grant-2" in await load_approval_grants()

    await remove_approval_grant("grant-2")

    assert "grant-2" not in await load_approval_grants()


@pytest.mark.asyncio
async def test_cleanup_removes_expired_entries(tmp_path):
    import koda.config as config_module

    fp = config_module.STATE_ROOT_DIR / "approval_grants.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    fp.write_text(
        json.dumps(
            {
                "alive": {"grant_id": "alive", "expires_at": now + 600},
                "dead": {"grant_id": "dead", "expires_at": now - 100},
            }
        ),
        encoding="utf-8",
    )

    await cleanup_expired_approval_grants()

    payload = json.loads(fp.read_text(encoding="utf-8"))
    assert "alive" in payload
    assert "dead" not in payload
