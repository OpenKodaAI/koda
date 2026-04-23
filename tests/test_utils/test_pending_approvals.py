"""Tests for the pending-approvals persistence layer."""

import json
import time

import pytest

from koda.state.pending_approvals import (
    cleanup_expired_ops,
    load_pending_ops,
    remove_pending_op,
    save_pending_op,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Point STATE_ROOT_DIR at a temp directory for each test."""
    import koda.config as config_module

    monkeypatch.setattr(config_module, "STATE_ROOT_DIR", tmp_path)


# ------------------------------------------------------------------
# save + load round-trip
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_load_round_trip(tmp_path):
    await save_pending_op("op1", {"user_id": 42, "description": "/rm foo", "op_type": "user"}, ttl_seconds=300)
    ops = await load_pending_ops()
    assert "op1" in ops
    assert ops["op1"]["user_id"] == 42
    assert ops["op1"]["description"] == "/rm foo"
    assert ops["op1"]["op_type"] == "user"


@pytest.mark.asyncio
async def test_multiple_ops_round_trip():
    await save_pending_op("a", {"user_id": 1, "description": "x", "op_type": "user"}, ttl_seconds=300)
    await save_pending_op("b", {"user_id": 2, "description": "y", "op_type": "agent_cmd"}, ttl_seconds=300)
    ops = await load_pending_ops()
    assert len(ops) == 2
    assert ops["b"]["op_type"] == "agent_cmd"


@pytest.mark.asyncio
async def test_agent_cmd_round_trip_preserves_requests_and_preview():
    await save_pending_op(
        "agent-1",
        {
            "user_id": 2,
            "description": "approve file deletion",
            "op_type": "agent_cmd",
            "agent_id": "agent-a",
            "preview_text": "Tool: file_delete",
            "requests": [
                {
                    "envelope": {
                        "tool_id": "file_delete",
                        "integration_id": "fileops",
                        "action_id": "file_delete",
                        "transport": "internal",
                        "access_level": "destructive",
                        "risk_class": "destructive",
                        "resource_scope_fingerprint": "scope-fp",
                        "params_fingerprint": "params-fp",
                    },
                    "approval_scope": {"kind": "scope", "ttl_seconds": 900, "max_uses": 10},
                }
            ],
        },
        ttl_seconds=300,
    )

    ops = await load_pending_ops()
    assert ops["agent-1"]["agent_id"] == "agent-a"
    assert ops["agent-1"]["preview_text"] == "Tool: file_delete"
    assert ops["agent-1"]["requests"][0]["envelope"]["tool_id"] == "file_delete"


# ------------------------------------------------------------------
# Expired ops are filtered on load
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_ops_filtered_on_load(tmp_path):
    import koda.config as config_module

    fp = config_module.STATE_ROOT_DIR / "pending_approvals.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    data = {
        "alive": {
            "op_id": "alive",
            "user_id": 1,
            "description": "d",
            "created_at": now,
            "expires_at": now + 600,
            "op_type": "user",
        },
        "dead": {
            "op_id": "dead",
            "user_id": 2,
            "description": "d",
            "created_at": now - 700,
            "expires_at": now - 100,
            "op_type": "user",
        },
    }
    fp.write_text(json.dumps(data), encoding="utf-8")

    ops = await load_pending_ops()
    assert "alive" in ops
    assert "dead" not in ops


# ------------------------------------------------------------------
# remove_pending_op
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_pending_op():
    await save_pending_op("r1", {"user_id": 5, "description": "x", "op_type": "user"}, ttl_seconds=300)
    await remove_pending_op("r1")
    ops = await load_pending_ops()
    assert "r1" not in ops


@pytest.mark.asyncio
async def test_remove_nonexistent_op():
    """Removing an op that doesn't exist should not raise."""
    await remove_pending_op("nope")


# ------------------------------------------------------------------
# cleanup_expired_ops
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_expired_ops(tmp_path):
    import koda.config as config_module

    fp = config_module.STATE_ROOT_DIR / "pending_approvals.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    data = {
        "good": {
            "op_id": "good",
            "user_id": 1,
            "description": "d",
            "created_at": now,
            "expires_at": now + 600,
            "op_type": "user",
        },
        "expired": {
            "op_id": "expired",
            "user_id": 2,
            "description": "d",
            "created_at": now - 700,
            "expires_at": now - 100,
            "op_type": "user",
        },
    }
    fp.write_text(json.dumps(data), encoding="utf-8")

    await cleanup_expired_ops()

    raw = json.loads(fp.read_text(encoding="utf-8"))
    assert "good" in raw
    assert "expired" not in raw


# ------------------------------------------------------------------
# File doesn't exist on first load
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_empty_when_no_file():
    ops = await load_pending_ops()
    assert ops == {}
